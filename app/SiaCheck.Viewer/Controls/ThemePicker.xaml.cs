using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Bouton de thème (accueil, barre du projet) : ouvre un volet de vignettes, une ligne par palette (clair, sombre).
/// Les couleurs des vignettes sont lues dans les Colors.*.xaml eux-mêmes ; le choix passe par MainViewModel.SetTheme.
/// </summary>
public partial class ThemePicker : UserControl
{
    /// <summary>Volet fermé par le clic qui retombe sur le bouton : ce clic ne doit pas le rouvrir.</summary>
    private static readonly TimeSpan ReopenGuard = TimeSpan.FromMilliseconds(250);
    private static readonly Dictionary<string, ResourceDictionary> Previews = [];
    private DateTime _closedAt;

    public ThemePicker() => InitializeComponent();

    private MainViewModel? ViewModel => DataContext as MainViewModel;

    private void Toggle_Click(object sender, RoutedEventArgs e)
    {
        if (DateTime.Now - _closedAt < ReopenGuard || ViewModel is not { } vm) return;
        Families.ItemsSource = AppTheme.All
            .GroupBy(t => t.Family)
            .Select(g => new ThemeFamily(g.Key, g.OrderBy(t => t.IsDark).Select(t => Tile(t, t == vm.CurrentTheme)).ToList()))
            .ToList();
        Flyout.IsOpen = true;
        Dispatcher.BeginInvoke(() => Families.MoveFocus(new TraversalRequest(FocusNavigationDirection.First)),
                               System.Windows.Threading.DispatcherPriority.Input);
    }

    private void Flyout_Closed(object? sender, EventArgs e) => _closedAt = DateTime.Now;

    private void Flyout_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Escape) return;
        Flyout.IsOpen = false;
        Toggle.Focus();
        e.Handled = true;
    }

    private void Tile_Click(object sender, RoutedEventArgs e)
    {
        if (((FrameworkElement)sender).DataContext is ThemeTile tile) ViewModel?.SetThemeCommand.Execute(tile.Theme);
        Flyout.IsOpen = false;
    }

    private static ThemeTile Tile(AppTheme theme, bool current)
    {
        if (!Previews.TryGetValue(theme.Id, out var colors))
            Previews[theme.Id] = colors = new ResourceDictionary
            {
                Source = new Uri($"Themes/Colors.{theme.File}.xaml", UriKind.Relative),
            };
        Brush Of(string key) => (Brush)colors[key];
        return new ThemeTile(theme, theme.IsDark ? "Sombre" : "Clair", current, Of("BrushBackground"), Of("BrushSurface"),
                             Of("BrushDivider"), Of("BrushTextPrimary"), Of("BrushTextSecondary"), Of("BrushAccent"));
    }
}

public sealed record ThemeFamily(string Name, IReadOnlyList<ThemeTile> Tiles);

public sealed record ThemeTile(AppTheme Theme, string Variant, bool IsCurrent, Brush Background, Brush Surface,
                               Brush Divider, Brush Text, Brush Text2, Brush Accent);
