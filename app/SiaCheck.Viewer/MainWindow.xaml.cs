using System.ComponentModel;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Media3D;
using Microsoft.Win32;
using SiaCheck.Viewer.Services;
using SiaCheck.Viewer.ViewModels;
using Wpf.Ui;
using Wpf.Ui.Controls;

namespace SiaCheck.Viewer;

/// <summary>
/// Vue de l'espace de revue. Le code-behind se limite à ce qui touche la vue elle-même :
/// caméra, test d'impact 3D, raccourcis de la liste, notifications et placement de fenêtre.
/// </summary>
public partial class MainWindow : FluentWindow, IShell
{
    private const double ClickTolerance = 4;     // px : au-delà, c'est une rotation de caméra, pas un clic
    private const int CameraAnimationMs = 300;   // plan §7 : seule animation porteuse de sens
    private const double FrameMargin = 0.15;     // marge autour des surfaces isolées

    private readonly AppPaths _paths;
    private readonly AppSettings _settings;
    private readonly SnackbarService _snackbars = new();
    private Point _mouseDown;

    public MainViewModel ViewModel { get; }

    public MainWindow(AppPaths paths, AppSettings settings, string? enginePath)
    {
        _paths = paths;
        _settings = settings;
        InitializeComponent();
        ViewModel = new MainViewModel(this, paths, settings, enginePath);
        DataContext = ViewModel;
        _snackbars.SetSnackbarPresenter(Snackbars);
        ViewModel.PropertyChanged += OnViewModelChanged;
        ViewModel.LinkedIssuesChanged += OnLinkedIssues;
        ViewModel.TraceFitRequested += () => Dispatcher.InvokeAsync(() => { TracePlanControl.Fit(); TracePlanControl.Focus(); },
                                                                     System.Windows.Threading.DispatcherPriority.Loaded);
        TracePlanControl.CloseRequested += (_, _) => ViewModel.CancelTraceCommand.Execute(null);
        RestorePlacement();
        Viewport.PreviewMouseLeftButtonDown += (_, e) => _mouseDown = e.GetPosition(Viewport);
        Viewport.PreviewMouseLeftButtonUp += Viewport_Click;
        PreviewKeyDown += Window_PreviewKeyDown;
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(MainViewModel.Scene) or "")
            SceneVisual.Content = ViewModel.Scene?.Root;
    }

    // ------------------------------------------------------------------ IShell

    public string? PickFolder(string title, string? initial)
    {
        var dlg = new OpenFolderDialog { Title = title, InitialDirectory = initial ?? "" };
        return dlg.ShowDialog(this) == true ? dlg.FolderName : null;
    }

    public string? PickSaveFile(string title, string fileName, string filter)
    {
        var dlg = new SaveFileDialog { Title = title, FileName = fileName, Filter = filter, AddExtension = true };
        return dlg.ShowDialog(this) == true ? dlg.FileName : null;
    }

    public string? PickOpenFile(string title, string filter)
    {
        var dlg = new OpenFileDialog { Title = title, Filter = filter };
        return dlg.ShowDialog(this) == true ? dlg.FileName : null;
    }

    public void Notify(string message, bool isError = false) =>
        _snackbars.Show(isError ? "Erreur" : "Information", message,
                        isError ? ControlAppearance.Danger : ControlAppearance.Secondary,
                        new SymbolIcon(isError ? SymbolRegular.ErrorCircle24 : SymbolRegular.Info24),
                        TimeSpan.FromSeconds(isError ? 8 : 4));

    public async Task<bool> ConfirmAsync(string title, string message, string yes, string no)
    {
        var box = new Wpf.Ui.Controls.MessageBox
        {
            Title = title, Content = message, PrimaryButtonText = yes, CloseButtonText = no, Owner = this,
        };
        return await box.ShowDialogAsync() == Wpf.Ui.Controls.MessageBoxResult.Primary;
    }

    public async Task<string[]?> AskAsync(string title, string message, IReadOnlyList<(string Label, string Value)> fields, string ok)
    {
        var panel = new StackPanel { MinWidth = 360 };
        panel.Children.Add(new System.Windows.Controls.TextBlock { Text = message, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12) });
        var boxes = new List<System.Windows.Controls.TextBox>();
        foreach (var (label, value) in fields)
        {
            panel.Children.Add(new System.Windows.Controls.TextBlock { Text = label, Margin = new Thickness(0, 8, 0, 4) });
            var box = new System.Windows.Controls.TextBox { Text = value };
            boxes.Add(box);
            panel.Children.Add(box);
        }
        var dlg = new Wpf.Ui.Controls.MessageBox
        {
            Title = title, Content = panel, PrimaryButtonText = ok, CloseButtonText = "Annuler", Owner = this,
        };
        dlg.Loaded += (_, _) => { boxes[0].Focus(); boxes[0].SelectAll(); };
        return await dlg.ShowDialogAsync() == Wpf.Ui.Controls.MessageBoxResult.Primary
            ? boxes.Select(b => b.Text.Trim()).ToArray() : null;
    }

    public void OpenFile(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });

    public void Frame(Rect3D? bounds)
    {
        var ms = SystemParameters.ClientAreaAnimation ? CameraAnimationMs : 0;
        Dispatcher.InvokeAsync(() =>
        {
            if (bounds is not { } b || b.IsEmpty) { Viewport.ZoomExtents(ms); return; }
            var m = Math.Max(Math.Max(b.SizeX, b.SizeY), 4) * FrameMargin;
            Viewport.ZoomExtents(new Rect3D(b.X - m, b.Y - m, b.Z - m, b.SizeX + 2 * m, b.SizeY + 2 * m, b.SizeZ + 2 * m), ms);
        }, System.Windows.Threading.DispatcherPriority.Loaded);
    }

    public void ApplyTheme(string theme) => App.ApplyTheme(theme);

    public Color GhostColor => (Color)FindResource("ColorGhost");

    public Color AccentColor => (Color)FindResource("ColorAccent");

    // ------------------------------------------------------------------ 3D

    private void Viewport_Click(object sender, MouseButtonEventArgs e)
    {
        var p = e.GetPosition(Viewport);
        if ((p - _mouseDown).Length > ClickTolerance) return;
        ClickAt(p);
    }

    /// <summary>Sélectionne la surface sous ce point de la vue 3D (aussi utilisé par --click pour la revue visuelle).</summary>
    public void ClickAt(Point p)
    {
        if (ViewModel.Scene is null) return;
        string? hit = null;
        VisualTreeHelper.HitTest(Viewport.Viewport, null, r =>
        {
            if (r is RayMeshGeometry3DHitTestResult m && m.ModelHit is GeometryModel3D g &&
                ViewModel.Scene.SurfaceAt(g, m.VertexIndex1) is { } id)
            {
                hit = id;
                return HitTestResultBehavior.Stop;
            }
            return HitTestResultBehavior.Continue;
        }, new PointHitTestParameters(p));
        ViewModel.SelectSurface(hit);
    }

    public void ClickAtRelative(double x, double y) => ClickAt(new Point(x * Viewport.ActualWidth, y * Viewport.ActualHeight));

    private void TopView_Click(object sender, RoutedEventArgs e) => TopView();

    private void TopView()
    {
        if (Viewport.Camera is not ProjectionCamera cam) return;
        cam.LookDirection = new Vector3D(0, 0, -Math.Max(cam.LookDirection.Length, 50));
        cam.UpDirection = new Vector3D(0, 1, 0);
        Viewport.ZoomExtents(SystemParameters.ClientAreaAnimation ? CameraAnimationMs : 0);
    }

    private void CloseSurface_Click(object sender, RoutedEventArgs e) => ViewModel.SelectSurface(null);

    // ------------------------------------------------------------------ revue IA

    /// <summary>La clé ne transite que par le PasswordBox : jamais liée, vidée dès qu'elle est chiffrée.</summary>
    private void SaveApiKey_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.SaveApiKeyCommand.Execute(ApiKeyBox.Password);
        ApiKeyBox.Password = "";
    }

    private void ApiKeyBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter) return;
        SaveApiKey_Click(sender, e);
        e.Handled = true;
    }

    // ------------------------------------------------------------------ clavier et liste

    /// <summary>Clic sur un point : l'isole ; reclic sur le point isolé : quitte l'isolement.</summary>
    private void IssuesList_Click(object sender, MouseButtonEventArgs e)
    {
        if (ItemsControl.ContainerFromElement(IssuesList, (DependencyObject)e.OriginalSource) is ListBoxItem { DataContext: IssueItem item })
            ViewModel.ToggleFocusCommand.Execute(item);
    }

    /// <summary>Clic sur le sujet déjà ouvert : sa fiche se ferme.</summary>
    private void SubjectsList_PreviewMouseDown(object sender, MouseButtonEventArgs e)
    {
        if (ItemsControl.ContainerFromElement(SubjectsList, (DependencyObject)e.OriginalSource) is ListBoxItem { DataContext: SubjectItem item }
            && ReferenceEquals(item, ViewModel.SelectedSubject))
        {
            ViewModel.CloseSubjectCommand.Execute(null);
            e.Handled = true;
        }
    }

    private void OnLinkedIssues(IssueItem? first)
    {
        if (first is not null) IssuesList.ScrollIntoView(first);
    }

    private void IssuesList_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        var status = e.Key switch
        {
            Key.D1 or Key.NumPad1 => "todo",
            Key.D2 or Key.NumPad2 => "seen",
            Key.D3 or Key.NumPad3 => "false",
            _ => null,
        };
        if (status is not null) { ViewModel.SetStatusCommand.Execute(status); e.Handled = true; }
        else if (e.Key == Key.Enter) { ViewModel.ToggleFocusCommand.Execute(ViewModel.SelectedIssue); e.Handled = true; }
    }

    /// <summary>1 / 2 / 3 sur la correction sélectionnée : proposée / acceptée / rejetée (comme les statuts de points).</summary>
    private void CorrectionsList_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        var decision = e.Key switch
        {
            Key.D1 or Key.NumPad1 => "proposed",
            Key.D2 or Key.NumPad2 => "accepted",
            Key.D3 or Key.NumPad3 => "rejected",
            _ => null,
        };
        if (decision is not null) { ViewModel.SetCorrectionDecisionCommand.Execute(decision); e.Handled = true; }
        else if (e.Key == Key.F2) { ViewModel.EditCorrectionCommand.Execute(null); e.Handled = true; }
    }

    /// <summary>Édition d'une correction : Entrée enregistre, Échap annule (sans quitter l'isolement).</summary>
    private void CorrectionEdit_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Keyboard.Modifiers == ModifierKeys.None && Keyboard.FocusedElement is not System.Windows.Controls.TextBox { AcceptsReturn: true })
        {
            ViewModel.CommitCorrectionEditCommand.Execute(null);
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            ViewModel.CancelCorrectionEditCommand.Execute(null);
            e.Handled = true;
        }
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        // Volet Tracé : le plan reçoit ses propres touches (Échap, F, flèches…) ; hors du plan, Échap ferme le volet.
        if (ViewModel.IsTraceOpen)
        {
            if (TracePlanControl.IsKeyboardFocusWithin || Keyboard.FocusedElement is TextBoxBase or ComboBox) return;
            if (e.Key == Key.Escape) { ViewModel.CancelTraceCommand.Execute(null); e.Handled = true; }
            return;
        }
        // Échap ferme d'abord la boîte Revue IA (hors revue en cours), puis le rapport, avant de quitter l'isolement.
        if (e.Key == Key.Escape && ViewModel is { IsAiPanelOpen: true, IsAiRunning: false })
        {
            ViewModel.CloseAiPanelCommand.Execute(null);
            e.Handled = true;
            return;
        }
        if (e.Key == Key.Escape && ViewModel.IsAiReportOpen)
        {
            ViewModel.CloseAiReportCommand.Execute(null);
            e.Handled = true;
            return;
        }
        // Raccourcis à une touche : jamais pendant la saisie d'un commentaire ou d'un filtre.
        if (Keyboard.FocusedElement is TextBoxBase or ComboBox || Keyboard.Modifiers != ModifierKeys.None) return;
        switch (e.Key)
        {
            case Key.F when ViewModel.SelectedIssue is not null:
                ViewModel.FocusIssueCommand.Execute(ViewModel.SelectedIssue);
                e.Handled = true;
                break;
            case Key.T when ViewModel is { ShowSubjects: true, CanTraceSelected: true }:
                ViewModel.OpenTraceForCorrectionCommand.Execute(null);   // T sur une correction : le module de tracé
                e.Handled = true;
                break;
            case Key.T when ViewModel.HasDocument:
                TopView();
                e.Handled = true;
                break;
        }
    }

    private void Splitter_DragCompleted(object sender, DragCompletedEventArgs e)
    {
        _settings.IssuesPanelWidth = IssuesColumn.ActualWidth;
        _settings.Save(_paths);
    }

    // ------------------------------------------------------------------ placement

    private void RestorePlacement()
    {
        var w = _settings.Window;
        Width = Math.Max(w.Width, MinWidth);
        Height = Math.Max(w.Height, MinHeight);
        if (w is { Left: { } left, Top: { } top } && left >= SystemParameters.VirtualScreenLeft &&
            left < SystemParameters.VirtualScreenLeft + SystemParameters.VirtualScreenWidth - 100)
        {
            WindowStartupLocation = WindowStartupLocation.Manual;
            Left = left;
            Top = top;
        }
        else WindowStartupLocation = WindowStartupLocation.CenterScreen;
        if (w.Maximized) WindowState = WindowState.Maximized;
        IssuesColumn.Width = new GridLength(Math.Max(_settings.IssuesPanelWidth, 320));
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        var b = RestoreBounds;
        _settings.Window = new WindowPlacement
        {
            Left = b.Left, Top = b.Top, Width = b.Width, Height = b.Height,
            Maximized = WindowState == WindowState.Maximized,
        };
        _settings.Save(_paths);
        base.OnClosing(e);
    }
}
