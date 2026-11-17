namespace SiaCheck.Viewer.Models;

/// <summary>
/// Calques d'une analyse : groupe, visibilité d'emblée, surfaces comptées. Une seule règle pour l'onglet Calques de la
/// visionneuse et pour la maquette 3D web du dashboard (<see cref="Services.WebModel"/>).
/// </summary>
public static class LayerRules
{
    private static readonly string[] InteriorCodes = ["SP", "SN", "SU", "SUP", "SUT", "SUS", "SD", "SI", "SC", "SCP", "SCN"];

    public static string Group(CategoryInfo cat) =>
        cat.Status == "unknown" ? "Codes inconnus"
        : cat.Family == "enveloppe" ? "Enveloppe"     // façades, vitrages : verticales, hors sommes
        : cat.Status != "ignored" && InteriorCodes.Contains(cat.Code) ? "Intérieur"   // SUT : code maison compté dans la SU
        : cat.Status == "ignored" || cat.Family == "custom" ? "USPI · Maison"
        : cat.Family == "uspi" ? "USPI · Maison"
        : InteriorCodes.Contains(cat.Code) ? "Intérieur" : "Extérieur";

    /// <summary>Intérieur et extérieur visibles d'emblée, et les toitures (SPT).</summary>
    public static bool VisibleByDefault(string group, string code) => group is "Intérieur" or "Extérieur" || code == "SPT";

    /// <summary>
    /// Surfaces d'une catégorie comptées dans le calque, hors exclues. Même règle que le moteur : le détail fait foi, le
    /// total de niveau sert quand il n'y a pas de détail.
    /// </summary>
    public static List<Surface> Counted(ViewerDocument doc, string code)
    {
        var surfaces = doc.Surfaces.Where(s => s.DisplayCode == code && !s.IsExcluded).ToList();
        return surfaces.Any(s => !s.IsLevelTotal) ? surfaces.Where(s => !s.IsLevelTotal).ToList() : surfaces;
    }
}
