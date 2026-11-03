namespace SiaCheck.Viewer.Services;

/// <summary>
/// Thème d'interface : un dictionnaire Themes/Colors.{File}.xaml (mêmes clés pour tous), le thème Fluent de base
/// (sombre ou clair) et l'identifiant passé au dashboard (data-theme de dashboard/style.css).
/// </summary>
public sealed record AppTheme(string Id, string Label, string File, bool IsDark, string DashboardId)
{
    public const string DefaultId = "Pervenche.Dark";

    /// <summary>Palette du thème (« Mint » pour « Mint sombre ») : une ligne du sélecteur de thème.</summary>
    public string Family => Label.Split(' ')[0];

    public static IReadOnlyList<AppTheme> All { get; } =
    [
        new("Pervenche.Dark", "Pervenche sombre", "Pervenche.Dark", true, "dark"),
        new("Pervenche.Light", "Pervenche clair", "Pervenche.Light", false, "light"),
        // « Mint » et « Amber » : identifiants des versions claires, enregistrés avant l'ajout des sombres
        new("Mint", "Mint clair", "Mint.Light", false, "mint"),
        new("Mint.Dark", "Mint sombre", "Mint.Dark", true, "mint-dark"),
        new("Amber", "Amber clair", "Amber.Light", false, "amber"),
        new("Amber.Dark", "Amber sombre", "Amber.Dark", true, "amber-dark"),
    ];

    /// <summary>Thème d'un identifiant enregistré ; « Dark » et « Light » (avant les thèmes nommés) désignent Pervenche.</summary>
    public static AppTheme Find(string? id) => id switch
    {
        "Dark" => All[0],
        "Light" => All[1],
        _ => All.FirstOrDefault(t => t.Id == id) ?? All[0],
    };
}
