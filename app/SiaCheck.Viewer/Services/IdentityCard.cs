using System.Text.Json;
using System.Text.Json.Serialization;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Carte d'identité d'un projet de la base (docs/CARTE_IDENTITE.md), calculée par le moteur (sia_check.carte) et portée
/// par benchmark.json, projet par projet. Valeurs déjà mises en forme : la visionneuse les affiche telles quelles.
/// </summary>
public sealed class IdentityCard
{
    [JsonPropertyName("version")] public int Version { get; set; }
    /// <summary>Code de source → nom affiché (Maquette, Fiche projet, SIG fédéral…).</summary>
    [JsonPropertyName("sources")] public Dictionary<string, string> Sources { get; set; } = [];
    [JsonPropertyName("blocs")] public List<IdentityCardBlock> Blocks { get; set; } = [];
    /// <summary>Données reléguées hors de la carte (contrôle, contexte détaillé).</summary>
    [JsonPropertyName("annexe")] public List<IdentityCardField> Annex { get; set; } = [];
    [JsonPropertyName("remplis")] public int Filled { get; set; }
    [JsonPropertyName("total")] public int Total { get; set; }
    /// <summary>Le projet a une maquette 3D dans la base (emprise, hauteur, épaisseur calculées).</summary>
    [JsonPropertyName("maquette")] public bool HasModel { get; set; }
    /// <summary>Le projet a une fiche SIG dans la base.</summary>
    [JsonPropertyName("sig")] public bool HasSig { get; set; }

    /// <summary>En tête de la carte : volume du projet, forme bâtie, densité, typologie ; null dans une carte d'avant.</summary>
    [JsonPropertyName("entete")] public IdentityCardHeader? Header { get; set; }

    public string SourceName(string code) => Sources.TryGetValue(code, out var n) ? n : code;
}

public sealed class IdentityCardHeader
{
    [JsonPropertyName("forme"), JsonConverter(typeof(LenientText))] public string? Form { get; set; }
    [JsonPropertyName("densite"), JsonConverter(typeof(LenientText))] public string? Density { get; set; }
    [JsonPropertyName("typologie"), JsonConverter(typeof(LenientText))] public string? Typology { get; set; }
    /// <summary>Prismes du volume hors-sol (m, centrés) : un par bâtiment et suite d'étages de même emprise.</summary>
    [JsonPropertyName("volume")] public List<VolumePrism>? Volume { get; set; }
    /// <summary>« maquette » (tiré de la maquette 3D de la base) ou « schéma » (d'après la forme saisie).</summary>
    [JsonPropertyName("volume_origine")] public string? VolumeOrigin { get; set; }
    /// <summary>Plan d'implantation à échelle vraie (V7) : parcelle et emprise ; null sans l'une ni l'autre.</summary>
    [JsonPropertyName("implantation")] public IdentityCardImplantation? Implantation { get; set; }
}

/// <summary>
/// Plan d'implantation (moteur, sia_check.carte.implantation) : polygones [polygone][anneau][point] en mètres, centrés
/// sur la parcelle, nord en haut pour elle. L'emprise de la maquette, non géoréférencée, est posée au point de l'adresse
/// dans son orientation propre (<see cref="Located"/> false).
/// </summary>
public sealed class IdentityCardImplantation
{
    [JsonPropertyName("parcelle")] public List<List<List<List<double>>>> Parcel { get; set; } = [];
    [JsonPropertyName("emprise")] public List<List<List<List<double>>>> Footprint { get; set; } = [];
    [JsonPropertyName("parcelle_m2")] public double? ParcelArea { get; set; }
    [JsonPropertyName("emprise_m2")] public double? FootprintArea { get; set; }
    [JsonPropertyName("calee")] public bool Located { get; set; }
}

public sealed class VolumePrism
{
    /// <summary>Bâtiment du prisme : le pictogramme dessine bâtiment par bâtiment, du fond vers l'avant.</summary>
    [JsonPropertyName("b")] public string Building { get; set; } = "";
    [JsonPropertyName("z0")] public double Bottom { get; set; }
    [JsonPropertyName("z1")] public double Top { get; set; }
    /// <summary>Contour extérieur (anti-horaire) puis cours (horaires), en [x, y].</summary>
    [JsonPropertyName("anneaux")] public List<List<List<double>>> Rings { get; set; } = [];
}

public sealed class IdentityCardBlock
{
    [JsonPropertyName("nom")] public string Name { get; set; } = "";
    /// <summary>Identification, Contraintes, Réponse ou Performance.</summary>
    [JsonPropertyName("role")] public string Role { get; set; } = "";
    [JsonPropertyName("champs")] public List<IdentityCardField> Fields { get; set; } = [];
}

public sealed class IdentityCardField
{
    [JsonPropertyName("cle")] public string Key { get; set; } = "";
    [JsonPropertyName("donnee")] public string Label { get; set; } = "";
    [JsonPropertyName("valeur"), JsonConverter(typeof(LenientText))] public string? Value { get; set; }
    /// <summary>Lignes de détail [libellé, valeur] : par bâtiment, par catégorie, par typologie…</summary>
    [JsonPropertyName("details")] public List<List<string>> Details { get; set; } = [];
    [JsonPropertyName("unite")] public string Unit { get; set; } = "";
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("source")] public string Source { get; set; } = "";
    [JsonPropertyName("mode")] public string Mode { get; set; } = "";
    [JsonPropertyName("extraction")] public string Extraction { get; set; } = "";
    /// <summary>Dans le modèle de données : existe, ajouter, modifier, reléguer.</summary>
    [JsonPropertyName("statut")] public string Status { get; set; } = "";
    /// <summary>Qui a fourni la valeur (V7) : Saisie, IA, Proposé, MDP, Maquette, Calcul, SIG ; null sans valeur.</summary>
    [JsonPropertyName("origine"), JsonConverter(typeof(LenientText))] public string? Origin { get; set; }

    /// <summary>Qui fournit la donnée et comment (moteur, sia_check.carte.remplissage).</summary>
    [JsonPropertyName("remplissage")] public FieldFilling? Filling { get; set; }

    public bool IsFilled => !string.IsNullOrEmpty(Value) || Details.Count > 0;
}

/// <summary>
/// Mode de remplissage d'un champ : « vous » (saisie), « proposition » (proposé par SIA Check, à confirmer),
/// « identite » (fiche Identité du projet), « auto » (dès que les prérequis sont là), « demande » (autre équipe),
/// « module » (automatique quand le module existera).
/// </summary>
public sealed class FieldFilling
{
    [JsonPropertyName("mode")] public string Mode { get; set; } = "";
    [JsonPropertyName("texte")] public string Text { get; set; } = "";
    [JsonPropertyName("prerequis")] public List<string> Prerequisites { get; set; } = [];
    [JsonPropertyName("aide"), JsonConverter(typeof(LenientText))] public string? Help { get; set; }
    [JsonPropertyName("saisie")] public FieldInput? Input { get; set; }
}

/// <summary>Saisie d'un champ : la ligne d'InfosProjet du MDP qui la porte, son type, ses valeurs proposées.</summary>
public sealed class FieldInput
{
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    /// <summary>texte, nombre ou liste.</summary>
    [JsonPropertyName("type")] public string Type { get; set; } = "texte";
    [JsonPropertyName("options")] public List<string> Options { get; set; } = [];
    [JsonPropertyName("valeur"), JsonConverter(typeof(LenientText))] public string? Value { get; set; }
    /// <summary>Valeur proposée par SIA Check (forme bâtie, distribution), à confirmer.</summary>
    [JsonPropertyName("propose"), JsonConverter(typeof(LenientText))] public string? Proposed { get; set; }
}

/// <summary>Ce que la carte peut demander à l'application : enregistrer des saisies, ouvrir la fiche identité.</summary>
public sealed class IdentityCardActions
{
    /// <summary>Écrit les saisies (description InfosProjet → valeur) dans le MDP de la base, relit la base ; la carte à
    /// jour, ou null si l'écriture a échoué (le message est déjà affiché).</summary>
    public Func<IReadOnlyDictionary<string, string>, Task<IdentityCard?>>? SaveAsync { get; init; }
    /// <summary>Ouvre la fiche « Identité du projet » du MDP ; la carte à jour, ou null si annulée.</summary>
    public Func<Task<IdentityCard?>>? EditIdentityAsync { get; init; }
}

/// <summary>
/// Texte lu avec tolérance : un nombre ou un booléen devient du texte. Une valeur inattendue de la carte ne doit jamais
/// rendre benchmark.json illisible (la base entière disparaîtrait de l'accueil).
/// </summary>
public sealed class LenientText : JsonConverter<string?>
{
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) => reader.TokenType switch
    {
        JsonTokenType.String => reader.GetString(),
        JsonTokenType.Number => reader.TryGetInt64(out var i) ? i.ToString() : reader.GetDouble().ToString(System.Globalization.CultureInfo.InvariantCulture),
        JsonTokenType.True => "oui",
        JsonTokenType.False => "non",
        JsonTokenType.Null => null,
        _ => SkipAndNull(ref reader),
    };

    private static string? SkipAndNull(ref Utf8JsonReader reader)
    {
        reader.Skip();
        return null;
    }

    public override void Write(Utf8JsonWriter writer, string? value, JsonSerializerOptions options) => writer.WriteStringValue(value);
}
