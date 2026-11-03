namespace SiaCheck.Viewer.Services;

/// <summary>
/// Thème d'interface : un dictionnaire Themes/Colors.{File}.xaml (mêmes clés pour tous), le thème Fluent de base
/// (sombre ou clair) et l'identifiant passé au dashboard (data-theme de dashboard/style.css).
/// </summary>
public sealed record AppTheme(string Id, string Label, string File, bool IsDark, string DashboardId)
{
    public const string DefaultId = "Pervenche.Dark";

    public static IReadOnlyList<AppTheme> All { get; } =
    [
        new("Pervenche.Dark", "Pervenche sombre", "Pervenche.Dark", true, "dark"),
        new("Pervenche.Light", "Pervenche clair", "Pervenche.Light", false, "light"),
        new("Mint", "Mint", "Mint", false, "mint"),
        new("Amber", "Amber", "Amber", false, "amber"),
    ];

    /// <summary>Thème d'un identifiant enregistré ; « Dark » et « Light » (avant les thèmes nommés) désignent Pervenche.</summary>
    public static AppTheme Find(string? id) => id switch
    {
        "Dark" => All[0],
        "Light" => All[1],
        _ => All.FirstOrDefault(t => t.Id == id) ?? All[0],
    };
}
