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
        OnDashboardChanged(e.PropertyName);
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

    /// <summary>
    /// Fiche « Identité du projet » (docs/DESIGN_PLAN.md, Évolution 3.4) : listes du gabarit MDP là où elles existent,
    /// pour que la sélection du benchmark (typologie, canton) reste fiable ; * = nécessaire pour entrer dans la base.
    /// </summary>
    public async Task<MdpProject?> AskIdentityAsync(MdpProject initial, IdentityLists lists, IdentityMode mode, string ok)
    {
        var form = new IdentityForm(initial, lists, idReadOnly: mode == IdentityMode.EditBase);
        var dlg = new Wpf.Ui.Controls.MessageBox
        {
            Title = "Identité du projet", Content = form.Grid, PrimaryButtonText = ok, CloseButtonText = "Annuler", Owner = this,
            Width = DialogWidth, MaxWidth = DialogWidth,
        };
        form.Changed += () =>
        {
            var current = form.Read();
            var forBase = form.ShowReminder();
            dlg.IsPrimaryButtonEnabled = mode switch
            {
                IdentityMode.Base => forBase.Count == 0,
                IdentityMode.Export => current.Id.Length > 0,
                _ => true,
            };
        };
        form.Refresh();
        dlg.Loaded += (_, _) => form.Focus(mode == IdentityMode.EditBase);
        return await dlg.ShowDialogAsync() == Wpf.Ui.Controls.MessageBoxResult.Primary ? form.Read() : null;
    }

    /// <summary>Largeur des fiches : la boîte WPF-UI est plus étroite par défaut et coupait les champs.</summary>
    private const double DialogWidth = 680;

    /// <summary>
    /// Fiche projet (docs/DESIGN_PLAN.md, Évolutions 3.8 et 4.5) : l'identité d'abord, puis la source des données. À la
    /// création, un choix Treegram | Maquette IFC ; ensuite, la source du projet seule (maquette en lecture seule pour un
    /// projet généré). Seule une source valide est obligatoire ; les champs * restent un rappel pour le benchmark.
    /// </summary>
    public async Task<ProjectSheet?> AskProjectSheetAsync(ProjectSheet initial, IdentityLists lists, bool creating,
                                                         Func<ProjectSheet, SheetCheck> check)
    {
        System.Windows.Controls.TextBlock Section(string text, double top)
        {
            var s = new System.Windows.Controls.TextBlock { Text = text, Margin = new Thickness(0, top, 0, 6) };
            s.SetResourceReference(StyleProperty, "TextSection");
            return s;
        }
        System.Windows.Controls.TextBlock Caption(string text)
        {
            var c = new System.Windows.Controls.TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
            c.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty, "BrushTextSecondary");
            return c;
        }
        // Les chemins se choisissent dans l'explorateur (champ ou bouton), jamais au clavier
        (DockPanel Row, System.Windows.Controls.TextBox Box) PathRow(string text, string tooltip, Action browse, bool locked = false)
        {
            var box = new System.Windows.Controls.TextBox { Text = text, IsReadOnly = true, Cursor = locked ? null : Cursors.Hand,
                                                            ToolTip = locked ? text : tooltip };
            var row = new DockPanel();
            if (!locked)
            {
                var button = new Wpf.Ui.Controls.Button { Content = "Parcourir…", Margin = new Thickness(8, 0, 0, 0) };
                button.Click += (_, _) => browse();
                box.PreviewMouseLeftButtonUp += (_, e) => { e.Handled = true; browse(); };
                DockPanel.SetDock(button, Dock.Right);
                row.Children.Add(button);
            }
            row.Children.Add(box);
            return (row, box);
        }

        var ifcProject = !creating && initial.IsIfc;
        var form = new IdentityForm(initial.Identity, lists, idReadOnly: false);
        var state = new System.Windows.Controls.TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
        var idWarning = new System.Windows.Controls.TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
        idWarning.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty, "BrushVerdictWarning");

        var panel = new StackPanel { MinWidth = 560 };
        panel.Children.Add(Section("Identité", 0));
        panel.Children.Add(form.Grid);
        panel.Children.Add(idWarning);
        panel.Children.Add(Section(creating ? "Source des données" : ifcProject ? "Maquette IFC" : "Dossier Treegram", 20));

        // Source : Treegram (dossier .tgm + VWR) ou maquette IFC ; le choix n'existe qu'à la création
        var treegram = new System.Windows.Controls.RadioButton { Content = "Treegram", GroupName = "source", IsChecked = !initial.IsIfc, MinWidth = 120 };
        var ifc = new System.Windows.Controls.RadioButton { Content = "Maquette IFC", GroupName = "source", IsChecked = initial.IsIfc, Margin = new Thickness(16, 0, 0, 0) };
        if (creating)
        {
            var choice = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 8) };
            choice.Children.Add(treegram);
            choice.Children.Add(ifc);
            panel.Children.Add(choice);
        }

        System.Windows.Controls.TextBox folder = null!, model = null!;
        var outDir = initial.OutDir;
        var (folderRow, folderBox) = PathRow(initial.Folder, "Cliquer pour choisir le dossier dans l'explorateur", () =>
        {
            var dir = PickFolder("Dossier du projet Treegram (contient le fichier .tgm et le dossier VWR)", folder.Text.Length > 0 ? folder.Text : null);
            if (dir is null) return;
            folder.Text = dir;
            form.SuggestName(System.IO.Path.GetFileName(System.IO.Path.TrimEndingDirectorySeparator(dir)));
            form.Refresh();
        });
        folder = folderBox;
        var (modelRow, modelBox) = PathRow(initial.Ifc ?? "", "Cliquer pour choisir la maquette dans l'explorateur", () =>
        {
            var file = PickOpenFile("Maquette architecte IFC (avec ses IfcSpace)", "Maquette IFC|*.ifc");
            if (file is null) return;
            model.Text = file;
            form.SuggestName(System.IO.Path.GetFileNameWithoutExtension(file));
            form.Refresh();
        }, locked: ifcProject);
        model = modelBox;

        // Dossier des projets générés (création IFC) : le projet y prend son nom
        var outText = new System.Windows.Controls.TextBlock { TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center };
        outText.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty, "BrushTextSecondary");
        var change = new Wpf.Ui.Controls.Button { Content = "Changer…", Margin = new Thickness(8, 0, 0, 0), Appearance = ControlAppearance.Transparent };
        var outRow = new DockPanel { Margin = new Thickness(0, 6, 0, 0) };
        DockPanel.SetDock(change, Dock.Right);
        outRow.Children.Add(change);
        outRow.Children.Add(outText);
        void ShowOut() => outText.Text = $"Dossier des projets générés : {outDir}";
        change.Click += (_, _) =>
        {
            var dir = PickFolder("Dossier des projets générés", outDir);
            if (dir is null) return;
            outDir = dir;
            ShowOut();
            form.Refresh();
        };
        ShowOut();

        var ifcPanel = new StackPanel();
        ifcPanel.Children.Add(modelRow);
        if (creating)
        {
            ifcPanel.Children.Add(outRow);
            ifcPanel.Children.Add(Caption("La maquette doit contenir ses IfcSpace. La génération prend de 30 s à quelques minutes."));
        }
        else if (ifcProject)
            ifcPanel.Children.Add(Caption("↻ Régénérer, dans la liste des projets, relit cette maquette ; elle est redemandée si elle a été déplacée."));
        if (creating || !ifcProject) panel.Children.Add(folderRow);
        if (creating || ifcProject) panel.Children.Add(ifcPanel);
        panel.Children.Add(state);

        var dlg = new Wpf.Ui.Controls.MessageBox
        {
            Title = creating ? "Nouveau projet" : "Fiche projet", Content = panel, Owner = this,
            PrimaryButtonText = creating ? "Créer et analyser" : "Enregistrer", CloseButtonText = "Annuler",
            Width = DialogWidth, MaxWidth = DialogWidth,
            // La fiche grandit avec sa source (bloc IFC plus haut que le bloc Treegram) : jamais de champ coupé
            SizeToContent = SizeToContent.Height, MaxHeight = SystemParameters.WorkArea.Height - 40,
        };
        bool IsIfc() => ifcProject || creating && ifc.IsChecked == true;
        ProjectSheet Read() => IsIfc()
            ? new ProjectSheet(creating ? "" : initial.Folder, form.Read()) { Ifc = model.Text.Trim(), OutDir = creating ? outDir : null }
            : new ProjectSheet(folder.Text.Trim(), form.Read());
        void ShowSource()
        {
            if (!creating) return;
            folderRow.Visibility = IsIfc() ? Visibility.Collapsed : Visibility.Visible;
            ifcPanel.Visibility = IsIfc() ? Visibility.Visible : Visibility.Collapsed;
            dlg.PrimaryButtonText = IsIfc() ? "Créer et générer" : "Créer et analyser";
        }
        form.Changed += () =>
        {
            var c = check(Read());
            state.Text = c.FolderMessage;
            // Source pas encore choisie : une invitation, pas une erreur
            var chosen = (IsIfc() ? model.Text : folder.Text).Trim().Length > 0;
            state.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty,
                !c.FolderOk && chosen ? "BrushVerdictError" : c.FolderWarning ? "BrushVerdictWarning" : "BrushTextSecondary");
            idWarning.Text = c.IdWarning ?? "";
            idWarning.Visibility = c.IdWarning is null ? Visibility.Collapsed : Visibility.Visible;
            form.ShowReminder();
            // Bouton toujours visible (WPF-UI masque un bouton désactivé) : une source refusée est signalée à la validation
        };
        treegram.Checked += (_, _) => { ShowSource(); form.Refresh(); };
        ifc.Checked += (_, _) => { ShowSource(); form.Refresh(); };
        ShowSource();
        form.Refresh();
        dlg.Loaded += (_, _) => form.Focus(false);
        return await dlg.ShowDialogAsync() == Wpf.Ui.Controls.MessageBoxResult.Primary ? Read() : null;
    }

    /// <summary>Champs d'identité communs à la fiche Identité et à la fiche projet, avec le rappel des champs *.</summary>
    private sealed class IdentityForm
    {
        public Grid Grid { get; } = new() { MinWidth = 560 };
        public event Action? Changed;
        private readonly System.Windows.Controls.TextBox _id, _nom, _commune;
        private readonly System.Windows.Controls.ComboBox _typologie, _canton, _intervention, _phase;
        private readonly System.Windows.Controls.TextBlock _rappel;
        private bool _nameTouched;

        public IdentityForm(MdpProject initial, IdentityLists lists, bool idReadOnly)
        {
            Grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            _id = Add("ID projet HRS *", new System.Windows.Controls.TextBox { Text = initial.Id, IsReadOnly = idReadOnly });
            _nom = Add("Nom du projet *", new System.Windows.Controls.TextBox { Text = initial.Name });
            _typologie = Add("Typologie *", Liste(lists.Typologies, initial.Typologie, false));
            _canton = Add("Canton *", Liste(lists.Cantons, initial.Canton, false));
            _commune = Add("Commune", new System.Windows.Controls.TextBox { Text = initial.Commune });
            _intervention = Add("Type d'intervention *", Liste(lists.Interventions, initial.Intervention, false));
            _phase = Add("Phase SIA", Liste(lists.Phases, initial.Phase, true));
            if (idReadOnly) _id.ToolTip = "L'ID relie toutes les tables du MDP : il ne se modifie pas ici.";
            _nameTouched = initial.Name.Length > 0;

            _rappel = new System.Windows.Controls.TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) };
            _rappel.SetResourceReference(System.Windows.Controls.TextBlock.ForegroundProperty, "BrushTextSecondary");
            Grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Grid.SetRow(_rappel, Grid.RowDefinitions.Count - 1);
            Grid.SetColumnSpan(_rappel, 2);
            Grid.Children.Add(_rappel);

            foreach (var box in new[] { _id, _nom, _commune }) box.TextChanged += (_, _) => Changed?.Invoke();
            _nom.TextChanged += (_, _) => { if (_nom.IsKeyboardFocusWithin) _nameTouched = true; };
            foreach (var list in new[] { _typologie, _canton, _intervention, _phase }) list.SelectionChanged += (_, _) => Changed?.Invoke();
        }

        private T Add<T>(string label, T control) where T : FrameworkElement
        {
            var row = Grid.RowDefinitions.Count;
            Grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var text = new System.Windows.Controls.TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 6, 16, 6) };
            Grid.SetRow(text, row);
            Grid.SetRow(control, row);
            Grid.SetColumn(control, 1);
            control.Margin = new Thickness(0, 6, 0, 6);
            Grid.Children.Add(text);
            Grid.Children.Add(control);
            return control;
        }

        private static System.Windows.Controls.ComboBox Liste(IReadOnlyList<string> items, string value, bool optional)
        {
            // Une ancienne valeur hors liste (MDP rempli à la main) reste visible, en tête, pour être corrigée
            var all = new List<string>();
            if (optional) all.Add("");
            if (value.Length > 0 && !items.Contains(value)) all.Add(value);
            all.AddRange(items);
            return new System.Windows.Controls.ComboBox { ItemsSource = all, SelectedItem = value.Length > 0 ? value : (optional ? "" : null) };
        }

        public MdpProject Read() => new()
        {
            Id = _id.Text.Trim(), Name = _nom.Text.Trim(), Typologie = _typologie.SelectedItem as string ?? "",
            Canton = _canton.SelectedItem as string ?? "", Commune = _commune.Text.Trim(),
            Intervention = _intervention.SelectedItem as string ?? "", Phase = _phase.SelectedItem as string ?? "",
        };

        /// <summary>Nom du projet tiré du dossier, tant que l'utilisateur ne l'a pas saisi lui-même.</summary>
        public void SuggestName(string name)
        {
            if (!_nameTouched) _nom.Text = name;
        }

        public List<string> ShowReminder()
        {
            var forBase = ProjectIdentity.Missing(Read(), forBase: true);
            _rappel.Text = forBase.Count == 0
                ? "* nécessaire pour entrer dans le benchmark : tout est renseigné."
                : $"* nécessaire pour entrer dans le benchmark. Il manque : {string.Join(", ", forBase)}.";
            return forBase;
        }

        public void Refresh() => Changed?.Invoke();

        public void Focus(bool typologie) => (typologie ? (FrameworkElement)_typologie : _id).Focus();
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
