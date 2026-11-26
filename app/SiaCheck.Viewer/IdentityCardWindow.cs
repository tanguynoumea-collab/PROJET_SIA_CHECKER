using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using SiaCheck.Viewer.Services;
using Wpf.Ui.Controls;
using TextBlock = System.Windows.Controls.TextBlock;

namespace SiaCheck.Viewer;

/// <summary>
/// Carte d'identité d'un projet de la base (docs/CARTE_IDENTITE.md), ouverte au clic droit sur un projet de l'accueil.
/// Les blocs dans l'ordre contraintes → réponse → performance ; pour chaque donnée, sa valeur (ou « à collecter ») et
/// la source qui la fournit ; en infobulle, comment on l'extrait. Fenêtre non modale : on peut en ouvrir plusieurs pour
/// comparer des projets.
/// </summary>
public sealed class IdentityCardWindow : FluentWindow
{
    private IdentityCard _card;
    private readonly string _title;
    private readonly string _subtitle;
    private readonly IdentityCardActions _actions;
    private readonly StackPanel _header = new() { Margin = new Thickness(28, 8, 28, 12) };
    private readonly StackPanel _body = new();
    private bool _showMissing = true;

    // Couleur par source (repère seulement, même code que la page de la carte) : lisible sur fond clair et sombre
    internal static readonly Dictionary<string, Color> SourceColors = new()
    {
        ["MAQ"] = Color.FromRgb(0x3E, 0x9C, 0x7A), ["FICHE"] = Color.FromRgb(0x5B, 0x7F, 0xD0), ["SIG"] = Color.FromRgb(0x2F, 0x9F, 0xAE),
        ["CAD"] = Color.FromRgb(0x8E, 0x6C, 0xC4), ["REGL"] = Color.FromRgb(0xD0, 0x5A, 0x50), ["TRAV"] = Color.FromRgb(0xC8, 0x86, 0x2E),
        ["DEV"] = Color.FromRgb(0xC9, 0x5E, 0x97), ["OFS"] = Color.FromRgb(0x8A, 0x99, 0x3E), ["CALC"] = Color.FromRgb(0x8C, 0x93, 0x8F),
    };

    public IdentityCardWindow(string title, string subtitle, IdentityCard card, Window owner, IdentityCardActions? actions = null)
    {
        _card = card;
        _title = title;
        _subtitle = subtitle;
        _actions = actions ?? new IdentityCardActions();
        Owner = owner;
        Title = $"Carte d'identité · {title}";
        Icon = owner.Icon;
        Width = 1040;
        Height = Math.Min(900, SystemParameters.WorkArea.Height - 40);
        MinWidth = 720;
        MinHeight = 400;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        WindowBackdropType = WindowBackdropType.None;
        ExtendsContentIntoTitleBar = true;
        SetResourceReference(BackgroundProperty, "BrushBackground");
        SetResourceReference(FontFamilyProperty, "FontUI");
        SetResourceReference(FontSizeProperty, "FontSizeBody");
        SetResourceReference(ForegroundProperty, "BrushTextPrimary");

        var divider = new Border { Height = 1, Margin = new Thickness(28, 4, 28, 0) };
        divider.SetResourceReference(Border.BackgroundProperty, "BrushDivider");

        _body.Margin = new Thickness(28, 8, 28, 32);
        // En-tête (volume, forme, densité, typologie) dans le défilement : il part avec le reste de la carte
        var content = new StackPanel();
        content.Children.Add(_header);
        content.Children.Add(divider);
        content.Children.Add(_body);
        var scroll = new ScrollViewer { VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Content = content };

        // Barre de titre WPF UI, comme la fenêtre principale (sans elle, la fenêtre n'a ni bouton Fermer ni poignée)
        var bar = new TitleBar
        {
            Title = Title, ShowMinimize = false,
            Icon = new ImageIcon { Source = new System.Windows.Media.Imaging.BitmapImage(new Uri("pack://application:,,,/Assets/SiaCheck.png")) },
        };
        var root = new DockPanel();
        DockPanel.SetDock(bar, Dock.Top);
        root.Children.Add(bar);
        root.Children.Add(scroll);
        Content = root;
        PreviewKeyDown += (_, e) => { if (e.Key == System.Windows.Input.Key.Escape) Close(); };
        Render(card);
    }

    /// <summary>Affiche la carte (à l'ouverture, puis après chaque saisie enregistrée depuis « Compléter la carte »).</summary>
    private void Render(IdentityCard card)
    {
        _card = card;
        _header.Children.Clear();
        _header.Children.Add(Identity(_title, _subtitle, card.Header, Completion(card)));

        var summary = new WrapPanel { Margin = new Thickness(0, 14, 0, 0) };
        summary.Children.Add(Chip($"{card.Filled} données renseignées sur {card.Total}"));
        summary.Children.Add(Chip(card.HasModel ? "Maquette 3D : oui" : "Maquette 3D : non (emprise, hauteur, épaisseur à collecter)"));
        summary.Children.Add(Chip(card.HasSig ? "Fiche SIG : oui" : "Fiche SIG : non"));
        _header.Children.Add(summary);

        var toggle = new System.Windows.Controls.CheckBox { Content = "Afficher les données à collecter", IsChecked = _showMissing, Margin = new Thickness(0, 12, 0, 0) };
        toggle.Checked += (_, _) => { _showMissing = true; Build(); };
        toggle.Unchecked += (_, _) => { _showMissing = false; Build(); };
        _header.Children.Add(toggle);
        Build();
    }

    /// <summary>Jauge de remplissage et bouton « Compléter la carte », à droite de l'en-tête.</summary>
    private StackPanel Completion(IdentityCard card)
    {
        var panel = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(16, 0, 0, 0) };
        panel.Children.Add(new Controls.CompletionRing(card) { HorizontalAlignment = HorizontalAlignment.Center });
        var legend = new StackPanel { Margin = new Thickness(0, 8, 0, 0), HorizontalAlignment = HorizontalAlignment.Center };
        foreach (var (role, color) in Controls.CompletionRing.Roles)
        {
            var fields = card.Blocks.Where(b => b.Role == role).SelectMany(b => b.Fields).ToList();
            if (fields.Count == 0) continue;
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 1, 0, 1) };
            row.Children.Add(new Ellipse { Width = 8, Height = 8, Fill = new SolidColorBrush(color), Margin = new Thickness(0, 0, 6, 0), VerticalAlignment = VerticalAlignment.Center });
            var t = Secondary(new TextBlock { Text = $"{role} {fields.Count(f => f.IsFilled)}/{fields.Count}" });
            t.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
            row.Children.Add(t);
            legend.Children.Add(row);
        }
        panel.Children.Add(legend);
        var button = new Wpf.Ui.Controls.Button
        {
            Content = "Compléter la carte", Appearance = ControlAppearance.Primary, Margin = new Thickness(0, 12, 0, 0),
            Icon = new SymbolIcon { Symbol = SymbolRegular.DocumentEdit20 }, HorizontalAlignment = HorizontalAlignment.Stretch,
            ToolTip = "Ce que vous devez renseigner, ce que SIA Check remplira seul ensuite, et ce qui est à demander",
        };
        button.Click += (_, _) => OpenCompletion();
        panel.Children.Add(button);
        return panel;
    }

    private void OpenCompletion()
    {
        var w = new CompleteCardWindow(_title, _card, this, _actions);
        w.CardUpdated += Render;
        w.ShowDialog();
    }

    /// <summary>
    /// En tête, en premier : le volume du projet en rouge (comme les pictogrammes de forme de Density), puis le nom, la
    /// forme bâtie, la densité et la typologie.
    /// </summary>
    private static Grid Identity(string title, string subtitle, IdentityCardHeader? h, UIElement completion)
    {
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(340) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(completion, 2);
        grid.Children.Add(completion);

        var picture = new Border { Height = 240, CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1) };
        picture.SetResourceReference(Border.BorderBrushProperty, "BrushDivider");
        picture.SetResourceReference(Border.BackgroundProperty, "BrushSurface");
        if (h?.Volume is { Count: > 0 } volume)
            picture.Child = new Controls.VolumePictogram(volume) { Margin = new Thickness(4) };
        else
            picture.Child = Secondary(new TextBlock
            {
                Text = "Pas de maquette 3D ni de forme connue : le volume s'affichera quand la maquette sera publiée dans la base.",
                TextWrapping = TextWrapping.Wrap, TextAlignment = TextAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(16),
            });
        var left = new StackPanel { Margin = new Thickness(0, 0, 24, 0) };
        left.Children.Add(picture);
        if (h?.Implantation is { } plan && (plan.Parcel.Count > 0 || plan.Footprint.Count > 0))
            left.Children.Add(Implantation(plan));
        grid.Children.Add(left);

        var right = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        Grid.SetColumn(right, 1);
        right.Children.Add(Styled(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap }, "TextTitle"));
        if (subtitle.Length > 0)
            right.Children.Add(Secondary(new TextBlock { Text = subtitle, Margin = new Thickness(0, 4, 0, 0), TextWrapping = TextWrapping.Wrap }));
        void Line(string label, string? value)
        {
            var row = new StackPanel { Margin = new Thickness(0, 12, 0, 0) };
            var l = Secondary(new TextBlock { Text = label });
            l.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
            row.Children.Add(l);
            var v = new TextBlock { Text = string.IsNullOrEmpty(value) ? "à collecter" : value, TextWrapping = TextWrapping.Wrap };
            v.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeSubtitle");
            if (string.IsNullOrEmpty(value)) { v.FontStyle = FontStyles.Italic; Secondary(v); }
            else v.SetResourceReference(FontFamilyProperty, "FontUISemibold");
            row.Children.Add(v);
            right.Children.Add(row);
        }
        Line("Forme bâtie", h?.Form);
        Line("Densité", h?.Density);
        Line("Typologie", h?.Typology);
        if (h?.VolumeOrigin is { } origin)
        {
            var note = Secondary(new TextBlock
            {
                Text = origin == "maquette" ? "Volume tiré de la maquette 3D du projet (base)" : "Schéma d'après la forme saisie (pas de maquette 3D dans la base)",
                Margin = new Thickness(0, 12, 0, 0), TextWrapping = TextWrapping.Wrap,
            });
            note.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
            right.Children.Add(note);
        }
        grid.Children.Add(right);
        return grid;
    }

    /// <summary>Vignette d'implantation à échelle constante (1:5000, comme la planche du benchmark) et sa légende.</summary>
    private static StackPanel Implantation(IdentityCardImplantation plan)
    {
        var panel = new StackPanel { Margin = new Thickness(0, 10, 0, 0) };
        var frame = new Border { Height = 170, CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1) };
        frame.SetResourceReference(Border.BorderBrushProperty, "BrushDivider");
        frame.SetResourceReference(Border.BackgroundProperty, "BrushSurface");
        var drawing = new Controls.FootprintPlan(plan);
        frame.Child = drawing;
        panel.Children.Add(frame);
        var parts = new List<string>();
        if (plan.ParcelArea is { } pa) parts.Add($"parcelle {pa:N0} m² (trait)");
        if (plan.FootprintArea is { } fa) parts.Add($"emprise {fa:N0} m² (aplat)");
        var note = Secondary(new TextBlock
        {
            Text = $"Implantation au 1:5000 (échelle commune à tous les projets) · {string.Join(", ", parts)}"
                   + (plan.Footprint.Count > 0 && plan.Parcel.Count > 0 && !plan.Located
                       ? ". Maquette non géoréférencée : emprise posée à l'adresse, orientation indicative." : "."),
            TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0),
        });
        note.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
        drawing.Loaded += (_, _) => drawing.Dispatcher.BeginInvoke(() =>
        {
            if (drawing.Scale != 5000) note.Text = note.Text.Replace("au 1:5000 (échelle commune à tous les projets)", $"au 1:{drawing.Scale:N0} (projet plus grand que le cadre au 1:5000)");
        }, System.Windows.Threading.DispatcherPriority.Background);
        panel.Children.Add(note);
        return panel;
    }

    private void Build()
    {
        _body.Children.Clear();
        string? role = null;
        foreach (var block in _card.Blocks)
        {
            var fields = block.Fields.Where(f => _showMissing || f.IsFilled).ToList();
            if (fields.Count == 0) continue;
            if (block.Role != role)
            {
                role = block.Role;
                if (role == block.Name) { _body.Children.Add(Block(block.Name, fields, top: 8)); continue; }
                _body.Children.Add(Styled(new TextBlock { Text = RoleTitle(role), Margin = new Thickness(0, _body.Children.Count == 0 ? 8 : 28, 0, 0) },
                                          "TextSubtitle"));
            }
            _body.Children.Add(Block(block.Name, fields));
        }
        var annex = _card.Annex.Where(f => _showMissing || f.IsFilled).ToList();
        if (annex.Count > 0)
        {
            var expander = new Expander
            {
                Header = "Annexe : contexte détaillé et données de contrôle (hors de la carte)", Margin = new Thickness(0, 28, 0, 0),
                Content = Table(annex),
            };
            _body.Children.Add(expander);
        }
    }

    private static string RoleTitle(string role) => role switch
    {
        "Contraintes" => "Contraintes · ce que le projet a reçu",
        "Réponse" => "Réponse · ce qu'on en a fait",
        "Performance" => "Performance · ce que ça a rendu",
        _ => role,
    };

    private UIElement Block(string name, List<IdentityCardField> fields, double top = 14)
    {
        var panel = new StackPanel { Margin = new Thickness(0, top, 0, 0) };
        var filled = fields.Count(f => f.IsFilled);
        var head = new DockPanel { Margin = new Thickness(0, 0, 0, 6) };
        var count = Secondary(new TextBlock { Text = $"{filled} / {fields.Count}", VerticalAlignment = VerticalAlignment.Bottom });
        DockPanel.SetDock(count, Dock.Right);
        head.Children.Add(count);
        head.Children.Add(Styled(new TextBlock { Text = name }, "TextSection"));
        panel.Children.Add(head);
        panel.Children.Add(Table(fields));
        return panel;
    }

    private Border Table(List<IdentityCardField> fields)
    {
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2.2, GridUnitType.Star), MinWidth = 180 });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(3, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.6, GridUnitType.Star), MinWidth = 150 });
        for (var r = 0; r < fields.Count; r++)
        {
            var f = fields[r];
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            if (r > 0)
            {
                var line = new Border { Height = 1, VerticalAlignment = VerticalAlignment.Top };
                line.SetResourceReference(Border.BackgroundProperty, "BrushDivider");
                Grid.SetRow(line, r);
                Grid.SetColumnSpan(line, 3);
                grid.Children.Add(line);
            }
            var label = new TextBlock { Text = f.Label, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(12, 9, 12, 9), ToolTip = Tooltip(f) };
            label.SetResourceReference(FontFamilyProperty, "FontUISemibold");
            Place(grid, label, r, 0);
            Place(grid, Value(f), r, 1);
            Place(grid, SourceTag(f), r, 2);
        }
        var border = new Border { Child = grid, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6) };
        border.SetResourceReference(Border.BorderBrushProperty, "BrushDivider");
        border.SetResourceReference(Border.BackgroundProperty, "BrushSurface");
        return border;
    }

    private static void Place(Grid grid, UIElement e, int row, int col)
    {
        Grid.SetRow(e, row);
        Grid.SetColumn(e, col);
        grid.Children.Add(e);
    }

    private static UIElement Value(IdentityCardField f)
    {
        var panel = new StackPanel { Margin = new Thickness(0, 9, 12, 9) };
        if (!f.IsFilled)
        {
            panel.Children.Add(Secondary(new TextBlock { Text = "à collecter", FontStyle = FontStyles.Italic }));
            return panel;
        }
        if (!string.IsNullOrEmpty(f.Value))
            panel.Children.Add(new TextBlock { Text = f.Value, TextWrapping = TextWrapping.Wrap });
        foreach (var d in f.Details)
        {
            var line = d.Count >= 2 ? $"{d[0]} : {d[1]}" : string.Join(" ", d);
            panel.Children.Add(Secondary(new TextBlock { Text = line, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) }));
        }
        return panel;
    }

    private UIElement SourceTag(IdentityCardField f)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 9, 12, 9), VerticalAlignment = VerticalAlignment.Top,
                                   ToolTip = f.Mode };
        var color = SourceColors.TryGetValue(f.Source, out var c) ? c : Colors.Gray;
        row.Children.Add(new Ellipse { Width = 8, Height = 8, Fill = new SolidColorBrush(color), Margin = new Thickness(0, 0, 8, 0), VerticalAlignment = VerticalAlignment.Center });
        var texts = new StackPanel();
        texts.Children.Add(Secondary(new TextBlock { Text = _card.SourceName(f.Source), TextWrapping = TextWrapping.Wrap, MaxWidth = 190 }));
        // origine de la valeur (V7) : qui l'a fournie, quand le champ est renseigné
        if (!string.IsNullOrEmpty(f.Origin))
        {
            var origin = Secondary(new TextBlock { Text = $"Origine : {f.Origin}", TextWrapping = TextWrapping.Wrap, MaxWidth = 190, Margin = new Thickness(0, 2, 0, 0) });
            origin.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
            texts.Children.Add(origin);
        }
        row.Children.Add(texts);
        return row;
    }

    private string Tooltip(IdentityCardField f)
    {
        var unit = string.IsNullOrEmpty(f.Unit) ? "" : $" · {f.Unit}";
        var origin = string.IsNullOrEmpty(f.Origin) ? "" : $" · origine : {f.Origin}";
        return $"{f.Extraction}\n\n{f.Type}{unit} · {f.Mode} · source : {_card.SourceName(f.Source)}{origin} · statut : {f.Status}";
    }

    internal static TextBlock Styled(TextBlock t, string style)
    {
        t.SetResourceReference(StyleProperty, style);
        return t;
    }

    internal static TextBlock Secondary(TextBlock t)
    {
        t.SetResourceReference(TextBlock.ForegroundProperty, "BrushTextSecondary");
        return t;
    }

    internal static Border Chip(string text)
    {
        var t = new TextBlock { Text = text };
        t.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
        var b = new Border { Child = t, Padding = new Thickness(10, 3, 10, 3), Margin = new Thickness(0, 0, 8, 6), CornerRadius = new CornerRadius(10),
                             BorderThickness = new Thickness(1) };
        b.SetResourceReference(Border.BorderBrushProperty, "BrushDivider");
        b.SetResourceReference(Border.BackgroundProperty, "BrushSurface");
        return b;
    }
}
