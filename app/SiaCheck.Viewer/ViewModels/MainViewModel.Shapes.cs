using System.IO;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Forme des bâtiments proposée par l'IA (docs/V5_PLAN.md, partie 5) : la revue IA (bloc &lt;formes&gt;) et l'analyse IA
/// de la génération (generation/formes-ia.json) proposent une forme par bâtiment. Elle remplit la fiche quand la forme
/// est vide ou venait déjà de l'IA ; une forme saisie par l'utilisateur n'est remplacée qu'avec son accord.
/// </summary>
public partial class MainViewModel
{
    internal async Task ProposeShapesAsync(string projectDir, IReadOnlyDictionary<string, string> shapes)
    {
        if (shapes.Count == 0) return;
        var known = KnownIdentity(projectDir, Path.GetFileName(projectDir));
        var proposed = BuildingShapes.Encode(shapes);
        var label = BuildingShapes.Label(BuildingShapes.Decode(proposed));
        if (proposed.Length == 0 || BuildingShapes.Same(known.Forme, proposed)) return;
        var manual = known.Forme.Length > 0 && known.FormeOrigine != BuildingShapes.Ai;
        if (manual && !await _shell.ConfirmAsync("Remplacer la forme saisie ?",
                $"Forme saisie dans la fiche : {BuildingShapes.Label(BuildingShapes.Decode(known.Forme))}.\n" +
                $"Forme proposée par l'IA : {label}.",
                "Prendre la forme de l'IA", "Garder la saisie"))
            return;

        // fiche du projet : seule la forme change ; une fiche absente est créée pour la porter
        var sheet = _settings.FindMdpProject(projectDir) ?? new MdpProject();
        sheet.Forme = proposed;
        sheet.FormeOrigine = BuildingShapes.Ai;
        _settings.SetMdpProject(projectDir, sheet);
        _settings.Save(_paths);

        // projet déjà dans la base : son MDP fait foi pour le benchmark, la forme y est écrite aussi
        var inBase = BaseProject(known.Id);
        if (inBase is not null && _engine is not null && HasBenchmarkFolder)
        {
            var r = await _engine.WriteMdpIdentityAsync(Path.Combine(BenchmarkFolder, inBase.File),
                ProjectIdentity.WriteEngineFile(new MdpProject { Forme = proposed, FormeOrigine = BuildingShapes.Ai }, IdentityFile),
                CancellationToken.None);
            if (!r.Succeeded)
            {
                _shell.Notify($"Forme proposée par l'IA ({label}) enregistrée dans la fiche, pas dans le MDP de la base : {r.ErrorMessage}", isError: true);
                return;
            }
            await RefreshBenchmarkAsync();
        }
        _shell.Notify($"Forme proposée par l'IA : {label}. " +
                      (inBase is null ? "Enregistrée dans la fiche du projet." : "Enregistrée dans la fiche et dans le MDP de la base.") +
                      " Elle se corrige dans la fiche projet.");
    }
}
