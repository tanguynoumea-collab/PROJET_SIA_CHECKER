using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Remplir la carte d'identité avec l'IA de son choix (« Compléter la carte ») : un prompt prêt à envoyer avec les documents
/// du projet, qui impose un bloc de réponse ; puis la lecture de ce bloc, collé depuis la conversation.
///
/// Bloc imposé (une ligne par donnée, la source après la barre verticale) :
/// <code>
/// === SIA CHECK · CARTE D'IDENTITÉ · ID 1778 ===
/// Architecte = Atelier X | permis de construire, p. 2
/// Places vélo = ?
/// === FIN ===
/// </code>
/// « ? » : donnée absente des documents, ignorée. Les listes n'acceptent que leurs valeurs ; les nombres sont relus sans
/// unité. Rien n'est enregistré à la lecture : les champs sont pré-remplis, l'utilisateur vérifie puis enregistre.
/// </summary>
public static partial class CardPrompt
{
    public const string Start = "=== SIA CHECK · CARTE D'IDENTITÉ";
    public const string End = "=== FIN ===";

    /// <summary>Les champs à saisir de la carte (ceux que l'IA peut remplir), dans l'ordre de la carte.</summary>
    public static List<IdentityCardField> Inputs(IdentityCard card) =>
        card.Blocks.SelectMany(b => b.Fields).Where(f => f.Filling?.Input is not null).ToList();

    public static string Build(string project, string id, string? place, IdentityCard card)
    {
        var fields = Inputs(card);
        var sb = new StringBuilder();
        sb.AppendLine("Tu aides un service de développement immobilier suisse à documenter un projet de logement déjà réalisé.");
        sb.AppendLine($"Projet : « {project} » (ID {id}){(string.IsNullOrWhiteSpace(place) ? "" : $", {place}")}.");
        sb.AppendLine("Je joins des documents de ce projet (plans, descriptif, permis, plaquette, décompte, articles…).");
        sb.AppendLine();
        sb.AppendLine("Cherche dans ces documents la valeur de chaque donnée ci-dessous. Règles :");
        sb.AppendLine("- N'invente rien et ne déduis rien d'improbable : si la donnée n'est pas dans les documents, écris ?");
        sb.AppendLine("- Pour une liste, recopie exactement une des valeurs proposées.");
        sb.AppendLine("- Pour un nombre, écris le nombre seul, sans unité.");
        sb.AppendLine("- Après la valeur, indique la source après une barre verticale : document et page.");
        sb.AppendLine("- Une valeur actuelle est donnée quand elle existe : corrige-la seulement si les documents disent autre chose.");
        sb.AppendLine();
        sb.AppendLine("Données à trouver :");
        foreach (var f in fields)
        {
            var input = f.Filling!.Input!;
            var kind = input.Type switch
            {
                "liste" when input.Options.Count > 0 => "une valeur parmi : " + string.Join(" | ", input.Options),
                "nombre" => "nombre" + (string.IsNullOrEmpty(f.Unit) ? "" : $" (en {f.Unit})"),
                _ => "texte",
            };
            var current = input.Value ?? input.Proposed;
            sb.AppendLine($"- {input.Description} : {kind}. {f.Extraction}." +
                          (current is null ? "" : $" Valeur actuelle : {current}."));
        }
        sb.AppendLine();
        sb.AppendLine("Réponds uniquement avec le bloc suivant, rempli, dans un bloc de code pour qu'il se copie d'un seul clic.");
        sb.AppendLine("Ne change ni l'ordre ni le libellé des lignes, ni les lignes de début et de fin :");
        sb.AppendLine();
        sb.AppendLine("```");
        sb.Append(Template(id, fields));
        sb.AppendLine("```");
        return sb.ToString();
    }

    /// <summary>Le bloc vide à remplir.</summary>
    public static string Template(string id, IEnumerable<IdentityCardField> fields)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"{Start} · ID {id} ===");
        foreach (var f in fields) sb.AppendLine($"{f.Filling!.Input!.Description} = ");
        sb.AppendLine(End);
        return sb.ToString();
    }

    /// <summary>Une valeur relue dans le bloc : acceptée (normalisée) ou refusée, avec la raison.</summary>
    public sealed record Item(string Description, string Value, string? Source, bool Accepted, string? Reason);

    /// <summary>Résultat de la lecture : l'ID du bloc, les valeurs, et ce qui empêche de le lire.</summary>
    public sealed record Reading(string? Id, List<Item> Items, string? Error);

    public static Reading Parse(string text, IdentityCard card)
    {
        var lines = (text ?? "").Replace("\r", "").Split('\n').Select(l => l.Trim().Trim('`').Trim()).ToList();
        var start = lines.FindIndex(l => l.StartsWith(Start, StringComparison.OrdinalIgnoreCase));
        if (start < 0)
            return new Reading(null, [], "Aucun bloc « SIA CHECK · CARTE D'IDENTITÉ » dans le presse-papiers : copiez le bloc de réponse de l'IA.");
        var id = IdLine().Match(lines[start]) is { Success: true } m ? m.Groups[1].Value : null;
        var inputs = Inputs(card).Select(f => f.Filling!.Input!).ToDictionary(i => Key(i.Description));
        var items = new List<Item>();
        foreach (var line in lines.Skip(start + 1))
        {
            if (line.StartsWith("=== FIN", StringComparison.OrdinalIgnoreCase)) break;
            var eq = line.IndexOf('=');
            if (eq <= 0) continue;
            var desc = line[..eq].Trim().TrimStart('-', '*', ' ');
            var rest = line[(eq + 1)..].Trim();
            var bar = rest.IndexOf('|');
            var value = (bar >= 0 ? rest[..bar] : rest).Trim().Trim('"', '«', '»', ' ');
            var source = bar >= 0 ? rest[(bar + 1)..].Trim() : null;
            if (value.Length == 0 || value == "?" || Key(value) is "inconnu" or "non disponible" or "n/a" or "na") continue;
            if (!inputs.TryGetValue(Key(desc), out var input))
            {
                items.Add(new Item(desc, value, source, false, "donnée inconnue de la carte"));
                continue;
            }
            items.Add(Normalize(input, value, source));
        }
        return new Reading(id, items, null);
    }

    private static Item Normalize(FieldInput input, string value, string? source)
    {
        if (input.Type == "liste" && input.Options.Count > 0)
        {
            var exact = input.Options.FirstOrDefault(o => Key(o) == Key(value))
                        ?? input.Options.FirstOrDefault(o => Key(value).Contains(Key(o)) || Key(o).Contains(Key(value)));
            return exact is null
                ? new Item(input.Description, value, source, false, "valeur hors de la liste")
                : new Item(input.Description, exact, source, true, null);
        }
        if (input.Type == "nombre")
        {
            var m = Number().Match(value.Replace("'", "").Replace(" ", "").Replace(" ", ""));
            if (!m.Success) return new Item(input.Description, value, source, false, "nombre illisible");
            var n = double.Parse(m.Value.Replace(',', '.'), CultureInfo.InvariantCulture);
            return new Item(input.Description, n.ToString(CultureInfo.InvariantCulture), source, true, null);
        }
        return new Item(input.Description, value, source, true, null);
    }

    /// <summary>Clé de comparaison : minuscules, sans accents ni espaces doublés.</summary>
    public static string Key(string s)
    {
        var d = s.Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (var c in d)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(char.ToLowerInvariant(c));
        return Spaces().Replace(sb.ToString(), " ").Trim();
    }

    [GeneratedRegex(@"\bID\s+([\w.-]+)\s*===")]
    private static partial Regex IdLine();

    [GeneratedRegex(@"-?\d+(?:[.,]\d+)?")]
    private static partial Regex Number();

    [GeneratedRegex(@"\s+")]
    private static partial Regex Spaces();
}
