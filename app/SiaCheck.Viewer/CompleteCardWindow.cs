using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using SiaCheck.Viewer.Services;
using Wpf.Ui.Controls;
using TextBlock = System.Windows.Controls.TextBlock;
using TextBox = System.Windows.Controls.TextBox;

namespace SiaCheck.Viewer;

/// <summary>
/// « Compléter la carte » : ce qui manque à la carte d'identité, rangé par qui doit agir.
///   1. À vous : les saisies (écrites dans InfosProjet du MDP de la base), propositions de SIA Check pré-remplies ;
///      la fiche « Identité du projet » pour l'adresse, la catégorie, la phase ;
///   2. Automatique dès que… : les données que SIA Check remplira seul, groupées par prérequis manquant ;
///   3. À demander : ce qu'une autre équipe fournit, avec une demande prête à copier ;
///   4. Modules à venir : ce qui sera récupéré seul quand le module existera.
/// Le principe : l'utilisateur ne saisit que ce qu'aucun programme ne peut deviner.
/// </summary>
public sealed class CompleteCardWindow : FluentWindow
{
    private readonly string _project;
    private readonly IdentityCardActions _actions;
    private readonly StackPanel _body = new() { Margin = new Thickness(28, 8, 28, 16) };
    private readonly Dictionary<string, Func<string>> _inputs = [];      // description InfosProjet → valeur saisie
    private readonly Dictionary<string, string> _initial = [];
    private readonly Dictionary<string, string> _proposed = [];     // propositions de SIA Check pré-remplies
    private readonly Dictionary<string, Action<string, string?>> _setters = [];   // description → remplir (valeur, source IA)
    private IdentityCard _card;
    private readonly Wpf.Ui.Controls.Button _save;
    private readonly TextBlock _status = new() { VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap };

    /// <summary>La carte relue après un enregistrement : la carte d'identité ouverte se met à jour.</summary>
    public event Action<IdentityCard>? CardUpdated;

    public CompleteCardWindow(string project, IdentityCard card, Window owner, IdentityCardActions actions)
    {
        _project = project;
        _card = card;
        _actions = actions;
        Owner = owner;
        Title = $"Compléter la carte · {project}";
        Width = 900;
        Height = Math.Min(860, SystemParameters.WorkArea.Height - 60);
        MinWidth = 640;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        WindowBackdropType = WindowBackdropType.None;
        ExtendsContentIntoTitleBar = true;
        SetResourceReference(BackgroundProperty, "BrushBackground");
        SetResourceReference(FontFamilyProperty, "FontUI");
        SetResourceReference(FontSizeProperty, "FontSizeBody");
        SetResourceReference(ForegroundProperty, "BrushTextPrimary");

        var bar = new TitleBar { Title = Title, ShowMinimize = false, ShowMaximize = false };
        _save = new Wpf.Ui.Controls.Button
        {
            Content = "Enregistrer dans le MDP", Appearance = ControlAppearance.Primary, Icon = new SymbolIcon { Symbol = SymbolRegular.Save20 },
            IsEnabled = actions.SaveAsync is not null, Margin = new Thickness(12, 0, 0, 0),
            ToolTip = "Écrit vos saisies dans la feuille InfosProjet du MDP de la base, puis relit la base",
        };
        _save.Click += async (_, _) => await SaveAsync();
        var close = new Wpf.Ui.Controls.Button { Content = "Fermer", Margin = new Thickness(8, 0, 0, 0) };
        close.Click += (_, _) => Close();
        var footer = new DockPanel { Margin = new Thickness(28, 10, 28, 14) };
        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        buttons.Children.Add(_save);
        buttons.Children.Add(close);
        DockPanel.SetDock(buttons, Dock.Right);
        footer.Children.Add(buttons);
        footer.Children.Add(IdentityCardWindow.Secondary(_status));
        var line = new Border { Height = 1 };
        line.SetResourceReference(Border.BackgroundProperty, "BrushDivider");

        var root = new DockPanel();
        DockPanel.SetDock(bar, Dock.Top);
        DockPanel.SetDock(footer, Dock.Bottom);
        DockPanel.SetDock(line, Dock.Bottom);
        root.Children.Add(bar);
        root.Children.Add(footer);
        root.Children.Add(line);
        root.Children.Add(new ScrollViewer { VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Content = _body });
        Content = root;
        PreviewKeyDown += (_, e) => { if (e.Key == System.Windows.Input.Key.Escape) Close(); };
        Build();
    }

    private IEnumerable<IdentityCardField> Fields => _card.Blocks.SelectMany(b => b.Fields);
    private IEnumerable<IdentityCardField> Missing(string mode) =>
        Fields.Where(f => !f.IsFilled && f.Filling?.Mode == mode);

    private void Build()
    {
        _body.Children.Clear();
        _inputs.Clear();
        _initial.Clear();
        _proposed.Clear();
        _setters.Clear();
        var missing = Fields.Count(f => !f.IsFilled);
        var intro = new TextBlock
        {
            Text = $"{missing} données manquent à la carte de « {_project} ». Vous ne renseignez que ce qu'aucun programme ne peut " +
                   "deviner ; SIA Check remplit le reste seul dès que ses prérequis sont là.",
            TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0),
        };
        _body.Children.Add(intro);

        // 1. À vous : saisies (manquantes d'abord, puis celles déjà renseignées, modifiables)
        var inputs = Fields.Where(f => f.Filling?.Input is not null).OrderBy(f => f.IsFilled).ToList();
        var identity = Missing("identite").ToList();
        Section("À renseigner par vous", SymbolRegular.Person20, Color.FromRgb(0x5B, 0x7F, 0xD0),
                $"{inputs.Count(f => !f.IsFilled) + identity.Count} à compléter",
                "Écrit dans le MDP de la base. Les propositions de SIA Check sont pré-remplies : vérifiez-les puis enregistrez.");
        _body.Children.Add(AiBox());
        var grid = new Grid { Margin = new Thickness(0, 4, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(260) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var row = 0;
        foreach (var f in inputs)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var label = new StackPanel { Margin = new Thickness(0, 8, 12, 0) };
            label.Children.Add(new TextBlock { Text = f.Label, TextWrapping = TextWrapping.Wrap });
            var who = IdentityCardWindow.Secondary(new TextBlock { Text = _card.SourceName(f.Source), TextWrapping = TextWrapping.Wrap });
            who.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
            label.Children.Add(who);
            Grid.SetRow(label, row);
            grid.Children.Add(label);
            var editor = Editor(f.Filling!.Input!);
            Grid.SetRow(editor, row);
            Grid.SetColumn(editor, 1);
            grid.Children.Add(editor);
            row++;
        }
        _body.Children.Add(grid);
        if (identity.Count > 0)
        {
            var box = Box();
            var panel = new DockPanel();
            var open = new Wpf.Ui.Controls.Button
            {
                Content = "Ouvrir la fiche identité…", Icon = new SymbolIcon { Symbol = SymbolRegular.ContactCard20 },
                IsEnabled = _actions.EditIdentityAsync is not null, VerticalAlignment = VerticalAlignment.Center,
            };
            open.Click += async (_, _) => await EditIdentityAsync();
            DockPanel.SetDock(open, Dock.Right);
            panel.Children.Add(open);
            panel.Children.Add(new TextBlock
            {
                Text = "Fiche « Identité du projet » : " + string.Join(", ", identity.Select(f => f.Label.ToLowerInvariant())),
                TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0),
            });
            box.Child = panel;
            _body.Children.Add(box);
        }

        // 2. Automatique dès que… : groupé par prérequis manquant
        var auto = Missing("auto").ToList();
        if (auto.Count > 0)
        {
            Section("Rempli automatiquement dès que…", SymbolRegular.Flash20, Color.FromRgb(0x3E, 0x9C, 0x7A), $"{auto.Count} données",
                    "Rien à saisir champ par champ : il suffit de lever le prérequis.");
            foreach (var g in auto.GroupBy(f => f.Filling!.Prerequisites.Count > 0 ? string.Join(" + ", f.Filling.Prerequisites) : "Calcul de SIA Check"))
                _body.Children.Add(Group(g.Key, g.First().Filling!.Help, g.Select(f => f.Label)));
        }

        // 3. À demander
        var asks = Missing("demande").ToList();
        if (asks.Count > 0)
        {
            Section("À demander à une autre équipe", SymbolRegular.Mail20, Color.FromRgb(0xC8, 0x86, 0x2E), $"{asks.Count} données",
                    "Une demande prête à copier dans un mail ou dans Teams.");
            foreach (var g in asks.GroupBy(f => f.Filling!.Text.Replace("À demander : ", "")))
                _body.Children.Add(Group(g.Key, null, g.Select(f => f.Label), Request(g.Key, g.ToList())));
        }

        // 4. Modules à venir
        var modules = Missing("module").ToList();
        if (modules.Count > 0)
        {
            Section("Automatique, module à venir", SymbolRegular.Clock20, Color.FromRgb(0x8C, 0x93, 0x8F), $"{modules.Count} données",
                    "Prévu dans la roadmap : ces données seront récupérées sans saisie quand le module existera.");
            foreach (var g in modules.GroupBy(f => f.Filling!.Text.Replace("Automatique quand ce module existera : ", "")))
                _body.Children.Add(Group(g.Key, null, g.Select(f => f.Label)));
        }
        RefreshSave();
    }

    /// <summary>Champ de saisie : liste modifiable (valeurs proposées) ou texte ; pré-rempli par la valeur du MDP, sinon la
    /// proposition de SIA Check (marquée).</summary>
    private FrameworkElement Editor(FieldInput input)
    {
        var start = input.Value ?? input.Proposed ?? "";
        _initial[input.Description] = input.Value ?? "";
        if (input.Value is null && input.Proposed is not null) _proposed[input.Description] = input.Proposed;
        var panel = new StackPanel { Margin = new Thickness(0, 6, 0, 0) };
        var note = new TextBlock { Margin = new Thickness(0, 3, 0, 0), TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed };
        note.SetResourceReference(TextBlock.ForegroundProperty, "BrushAccentText");
        note.SetResourceReference(TextBlock.FontSizeProperty, "FontSizeCaption");
        Action<string> set;
        if (input.Type == "liste" && input.Options.Count > 0)
        {
            var combo = new ComboBox { IsEditable = true, ItemsSource = input.Options, Text = start, MinWidth = 280, HorizontalAlignment = HorizontalAlignment.Left };
            combo.AddHandler(System.Windows.Controls.Primitives.TextBoxBase.TextChangedEvent, new TextChangedEventHandler((_, _) => RefreshSave()));
            combo.SelectionChanged += (_, _) => Dispatcher.BeginInvoke(RefreshSave);
            panel.Children.Add(combo);
            _inputs[input.Description] = () => combo.Text.Trim();
            set = v => combo.Text = v;
        }
        else
        {
            var box = new TextBox { Text = start, MinWidth = 280, HorizontalAlignment = HorizontalAlignment.Left };
            if (input.Type == "nombre") box.Width = 140;
            box.TextChanged += (_, _) => RefreshSave();
            panel.Children.Add(box);
            _inputs[input.Description] = () => box.Text.Trim();
            set = v => box.Text = v;
        }
        panel.Children.Add(note);
        if (input.Value is null && input.Proposed is not null)
        {
            note.Text = "Proposé par SIA Check : à vérifier";
            note.Visibility = Visibility.Visible;
        }
        _setters[input.Description] = (v, source) =>
        {
            set(v);
            note.Text = "Rempli par l'IA : à vérifier" + (string.IsNullOrWhiteSpace(source) ? "" : $" (source : {source})");
            note.Visibility = Visibility.Visible;
        };
        return panel;
    }

    /// <summary>
    /// Remplir avec l'IA de son choix : le prompt (projet, données, valeurs permises, bloc de réponse imposé) part dans le
    /// presse-papiers ; on l'envoie avec les documents du projet ; on copie le bloc rendu par l'IA et on le colle ici.
    /// </summary>
    private Border AiBox()
    {
        var box = Box();
        var panel = new StackPanel();
        var head = new StackPanel { Orientation = Orientation.Horizontal };
        head.Children.Add(new SymbolIcon { Symbol = SymbolRegular.Sparkle20, Margin = new Thickness(0, 0, 8, 0), FontSize = 18 });
        var t = new TextBlock { Text = "Remplir avec une IA (ChatGPT, Copilot, Claude…)", VerticalAlignment = VerticalAlignment.Center };
        t.SetResourceReference(FontFamilyProperty, "FontUISemibold");
        head.Children.Add(t);
        panel.Children.Add(head);
        panel.Children.Add(new TextBlock
        {
            Text = "1. Copiez le prompt.  2. Collez-le dans l'IA avec les documents du projet (plans, descriptif, permis, plaquette, décompte…).  " +
                   "3. Copiez le bloc qu'elle répond et cliquez sur « Coller la réponse » : les champs se remplissent, vous vérifiez puis enregistrez.",
            TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 8),
        });
        var buttons = new WrapPanel();
        var prompt = new Wpf.Ui.Controls.Button
        {
            Content = "Copier le prompt IA", Appearance = ControlAppearance.Primary, Icon = new SymbolIcon { Symbol = SymbolRegular.Copy20 },
            Margin = new Thickness(0, 0, 8, 0), ToolTip = "Prompt prêt à envoyer, avec le bloc de réponse au format imposé",
        };
        prompt.Click += (_, _) => CopyPrompt();
        var paste = new Wpf.Ui.Controls.Button
        {
            Content = "Coller la réponse de l'IA", Icon = new SymbolIcon { Symbol = SymbolRegular.ClipboardPaste20 },
            ToolTip = "Lit le bloc « SIA CHECK · CARTE D'IDENTITÉ » copié depuis la conversation et remplit les champs",
        };
        paste.Click += (_, _) => PasteAnswer();
        buttons.Children.Add(prompt);
        buttons.Children.Add(paste);
        panel.Children.Add(buttons);
        box.Child = panel;
        return box;
    }

    private string ProjectId => Fields.FirstOrDefault(f => f.Key == "id")?.Value ?? "";

    private void CopyPrompt()
    {
        var place = Fields.FirstOrDefault(f => f.Key == "identite")?.Value;
        var text = CardPrompt.Build(_project, ProjectId, place, _card);
        try
        {
            Clipboard.SetText(text);
            _status.Text = $"Prompt copié ({CardPrompt.Inputs(_card).Count} données). Collez-le dans l'IA avec les documents du projet.";
        }
        catch (System.Runtime.InteropServices.ExternalException)
        {
            _status.Text = "Presse-papiers occupé : réessayez.";
        }
    }

    private void PasteAnswer()
    {
        string text;
        try
        {
            text = Clipboard.ContainsText() ? Clipboard.GetText() : "";
        }
        catch (System.Runtime.InteropServices.ExternalException)
        {
            _status.Text = "Presse-papiers occupé : réessayez.";
            return;
        }
        var reading = CardPrompt.Parse(text, _card);
        if (reading.Error is not null)
        {
            _status.Text = reading.Error;
            return;
        }
        if (reading.Id is not null && ProjectId.Length > 0 && !string.Equals(reading.Id, ProjectId, StringComparison.OrdinalIgnoreCase))
        {
            _status.Text = $"Ce bloc est celui du projet {reading.Id}, pas de {ProjectId} : rien n'a été repris.";
            return;
        }
        var taken = 0;
        foreach (var item in reading.Items.Where(i => i.Accepted))
        {
            var setter = _setters.FirstOrDefault(kv => CardPrompt.Key(kv.Key) == CardPrompt.Key(item.Description)).Value;
            if (setter is null) continue;
            setter(item.Value, item.Source);
            taken++;
        }
        var refused = reading.Items.Where(i => !i.Accepted).ToList();
        RefreshSave();
        _status.Text = $"{taken} valeur{(taken > 1 ? "s" : "")} reprise{(taken > 1 ? "s" : "")} de l'IA : vérifiez-les puis enregistrez." +
                       (refused.Count == 0 ? "" : $" Ignorées : " + string.Join(" ; ", refused.Select(r => $"{r.Description} ({r.Reason} : {r.Value})")));
    }

    private Dictionary<string, string> Changes() =>
        _inputs.Select(kv => (kv.Key, Value: kv.Value()))
               .Where(x => x.Value.Length > 0 && x.Value != _initial.GetValueOrDefault(x.Key, ""))
               .ToDictionary(x => x.Key, x => x.Value);

    private void RefreshSave()
    {
        var changes = Changes();
        var n = changes.Count;
        var proposals = changes.Count(kv => _proposed.GetValueOrDefault(kv.Key) == kv.Value);
        _save.IsEnabled = _actions.SaveAsync is not null && n > 0;
        _status.Text = _actions.SaveAsync is null ? "Enregistrement indisponible (moteur ou dossier de la base absent)."
            : n == 0 ? "Aucune modification."
            : $"{n} donnée{(n > 1 ? "s" : "")} à enregistrer" +
              (proposals > 0 ? $", dont {proposals} proposition{(proposals > 1 ? "s" : "")} de SIA Check à confirmer." : ".");
    }

    private async Task SaveAsync()
    {
        if (_actions.SaveAsync is null) return;
        var changes = Changes();
        if (changes.Count == 0) return;
        _save.IsEnabled = false;
        _status.Text = "Écriture dans le MDP et relecture de la base…";
        var card = await _actions.SaveAsync(changes);
        if (card is null)
        {
            RefreshSave();
            return;
        }
        _card = card;
        CardUpdated?.Invoke(card);
        Build();
        _status.Text = $"{changes.Count} donnée{(changes.Count > 1 ? "s" : "")} enregistrée{(changes.Count > 1 ? "s" : "")} dans le MDP.";
    }

    private async Task EditIdentityAsync()
    {
        if (_actions.EditIdentityAsync is null) return;
        var card = await _actions.EditIdentityAsync();
        if (card is null) return;
        _card = card;
        CardUpdated?.Invoke(card);
        Build();
    }

    // ----------------------------------------------------------------------------------------------- mise en forme

    private void Section(string title, SymbolRegular icon, Color color, string count, string note)
    {
        var head = new DockPanel { Margin = new Thickness(0, 24, 0, 2) };
        var badge = new Border { Width = 26, Height = 26, CornerRadius = new CornerRadius(13), Background = new SolidColorBrush(color), Margin = new Thickness(0, 0, 10, 0),
                                 Child = new SymbolIcon { Symbol = icon, Foreground = Brushes.White, FontSize = 14, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } };
        DockPanel.SetDock(badge, Dock.Left);
        head.Children.Add(badge);
        var c = IdentityCardWindow.Secondary(new TextBlock { Text = count, VerticalAlignment = VerticalAlignment.Center });
        DockPanel.SetDock(c, Dock.Right);
        head.Children.Add(c);
        head.Children.Add(IdentityCardWindow.Styled(new TextBlock { Text = title, VerticalAlignment = VerticalAlignment.Center }, "TextSubtitle"));
        _body.Children.Add(head);
        _body.Children.Add(IdentityCardWindow.Secondary(new TextBlock { Text = note, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(36, 0, 0, 6) }));
    }

    private static Border Box()
    {
        var b = new Border { Padding = new Thickness(14, 10, 14, 10), Margin = new Thickness(0, 6, 0, 0), CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1) };
        b.SetResourceReference(Border.BorderBrushProperty, "BrushDivider");
        b.SetResourceReference(Border.BackgroundProperty, "BrushSurface");
        return b;
    }

    private static Border Group(string title, string? help, IEnumerable<string> labels, UIElement? action = null)
    {
        var box = Box();
        var panel = new DockPanel();
        if (action is not null)
        {
            DockPanel.SetDock(action, Dock.Right);
            panel.Children.Add(action);
        }
        var text = new StackPanel { Margin = new Thickness(0, 0, action is null ? 0 : 12, 0) };
        var t = new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap };
        t.SetResourceReference(FontFamilyProperty, "FontUISemibold");
        text.Children.Add(t);
        if (help is not null)
            text.Children.Add(new TextBlock { Text = help, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 3, 0, 0) });
        var list = labels.ToList();
        text.Children.Add(IdentityCardWindow.Secondary(new TextBlock
        {
            Text = $"{list.Count} donnée{(list.Count > 1 ? "s" : "")} : " + string.Join(" · ", list),
            TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0),
        }));
        panel.Children.Add(text);
        box.Child = panel;
        return box;
    }

    /// <summary>Bouton « Copier la demande » : un texte prêt à envoyer, avec le projet et les données attendues.</summary>
    private UIElement Request(string who, List<IdentityCardField> fields)
    {
        var button = new Wpf.Ui.Controls.Button { Content = "Copier la demande", Icon = new SymbolIcon { Symbol = SymbolRegular.Copy20 }, VerticalAlignment = VerticalAlignment.Top };
        button.Click += (_, _) =>
        {
            var text = $"Bonjour,\n\nPour la carte d'identité du projet « {_project} » (benchmark SIA Check), pourrais-tu me transmettre :\n" +
                       string.Join("\n", fields.Select(f => $"- {f.Label} ({f.Extraction})")) + "\n\nMerci !";
            try
            {
                Clipboard.SetText(text);
                _status.Text = $"Demande copiée ({who}).";
            }
            catch (System.Runtime.InteropServices.ExternalException)
            {
                _status.Text = "Presse-papiers occupé : réessayez.";
            }
        };
        return button;
    }
}
