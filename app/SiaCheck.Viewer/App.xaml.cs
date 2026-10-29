using System.IO;
using System.Windows;
using SiaCheck.Viewer.Services;
using Wpf.Ui.Appearance;

namespace SiaCheck.Viewer;

public partial class App : Application
{
    private const int ColorsDictionaryIndex = 3;   // position de Colors.*.xaml dans App.xaml

    private static string CrashLog => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SiaCheckViewer", "crash.log");

    /// <summary>Toute exception non gérée est journalisée : un outil de revue ne doit pas mourir en silence.</summary>
    public static void LogCrash(Exception ex)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(CrashLog)!);
        File.AppendAllText(CrashLog, $"{DateTime.Now:O}\n{ex}\n\n");
    }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, a) =>
        {
            LogCrash(a.Exception);
            System.Windows.MessageBox.Show(
                $"Erreur inattendue : {a.Exception.Message}\n\nLe détail est enregistré dans {CrashLog}.",
                "SIA Check Viewer", MessageBoxButton.OK, MessageBoxImage.Error);
            a.Handled = true;
        };
        TaskScheduler.UnobservedTaskException += (_, a) => { LogCrash(a.Exception); a.SetObserved(); };
        // --profile dossier : profil isolé (statuts, journal, revues, analyses) pour les captures de revue visuelle.
        var paths = ArgAfter(e.Args, "--profile") is { } profile
            ? new AppPaths(System.IO.Path.Combine(profile, "roaming"), System.IO.Path.Combine(profile, "local"))
            : AppPaths.Default;
        var settings = AppSettings.Load(paths);
        ApplyTheme(settings.Theme);
        var engine = AnalysisService.Locate(AppContext.BaseDirectory);
        var window = new MainWindow(paths, settings, engine);
        MainWindow = window;
        window.Show();
        // SiaCheck.Viewer.exe "C:\…\Projects\L OREE" : ouvre directement un projet.
        // --capture fichier.png [--focus clé] [--subject id [--correction id]] [--points] [--report | --ai-panel] :
        // capture de la fenêtre puis fermeture
        // (revue visuelle, plan Phase 2 ; rapport et boîte de la revue IA, Évolution 1.1).
        var project = e.Args.FirstOrDefault(a => !a.StartsWith("--") && Directory.Exists(a));
        var capture = ArgAfter(e.Args, "--capture");
        // --analyse-ia-generation dossier : analyse IA d'un projet généré (V4, phase 24), avec estimation et accord.
        if (ArgAfter(e.Args, "--analyse-ia-generation") is { } generated && engine is not null)
            _ = AnalyseGeneratedAsync(window, paths, engine, generated);
        else if (project is not null) _ = OpenThenCaptureAsync(window, project, capture, ArgAfter(e.Args, "--focus"), ArgAfter(e.Args, "--click"));
        else if (capture is not null) _ = CaptureAsync(window, capture);
    }

    private static async Task AnalyseGeneratedAsync(MainWindow window, AppPaths paths, string engine, string dir)
    {
        const string title = "Analyse IA de la génération";
        try
        {
            await window.ViewModel.OpenAsync(dir);
            var key = new ApiKeyStore(paths.ApiKeyFile).Load();
            if (key is null)
            {
                MessageBox.Show(window, "Aucune clé API enregistrée : saisissez-la dans la revue IA de l'application.", title,
                                MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            var service = new AiGenerationService(new AnalysisService(engine));
            var prompt = await service.PrepareAsync(dir, CancellationToken.None);
            if (prompt.IssueCount == 0)
            {
                MessageBox.Show(window, "Les règles n'hésitent sur aucun espace : rien à demander à l'IA.", title);
                return;
            }
            var client = new AiReviewClient(key);
            var cost = await client.EstimateAsync(prompt, CancellationToken.None);
            var ok = MessageBox.Show(window,
                $"{prompt.IssueCount} espaces où les règles hésitent seront soumis à {AiPricing.ModelLabel}.\n\n" +
                $"Entrée : {cost.InputTokens:N0} jetons · sortie estimée : {cost.MinOutputTokens:N0} à {cost.MaxOutputTokens:N0} jetons.\n" +
                $"Coût estimé : {cost.MinUsd:0.00} à {cost.MaxUsd:0.00} $.\n\n" +
                "Les réponses deviennent des propositions : rien n'est appliqué sans votre accord. Lancer l'analyse ?",
                title, MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (ok != MessageBoxResult.Yes) return;
            var response = await client.RunAsync(prompt, null, CancellationToken.None);
            AiGenerationService.SaveResponse(dir, response, DateTime.Now);
            var summary = await service.RecordAsync(dir, CancellationToken.None);
            var text = File.Exists(AiGenerationService.SummaryPath(dir)) ? File.ReadAllText(AiGenerationService.SummaryPath(dir)) : "";
            MessageBox.Show(window, $"{summary.Replace("INFO ", "")}\nCoût réel : {response.CostUsd:0.00} $.\n\n{text}", title);
        }
        catch (AiReviewException ex)
        {
            MessageBox.Show(window, ex.Message, title, MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private static string? ArgAfter(string[] args, string flag)
    {
        var i = Array.IndexOf(args, flag);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    private static async Task OpenThenCaptureAsync(MainWindow window, string project, string? capture, string? focus, string? click)
    {
        try { await OpenThenCaptureCoreAsync(window, project, capture, focus, click); }
        catch (Exception ex)
        {
            LogCrash(ex);
            if (capture is not null) window.Close();
            else throw;
        }
    }

    private static async Task OpenThenCaptureCoreAsync(MainWindow window, string project, string? capture, string? focus, string? click)
    {
        await window.ViewModel.OpenAsync(project);
        if (focus is not null && window.ViewModel.Issues.FirstOrDefault(i => i.Key == focus) is { } item)
        {
            window.ViewModel.StatusFilter = "all";
            window.ViewModel.FocusIssueCommand.Execute(item);
        }
        // --click 0.5,0.5 : clic simulé en coordonnées relatives de la vue 3D, après le cadrage caméra.
        if (click?.Split(',') is [var cx, var cy])
        {
            await Task.Delay(TimeSpan.FromSeconds(1.5));
            window.ClickAtRelative(double.Parse(cx, System.Globalization.CultureInfo.InvariantCulture),
                                   double.Parse(cy, System.Globalization.CultureInfo.InvariantCulture));
        }
        // --subject S2 [--correction id] : onglet Sujets, sujet (et correction) sélectionnés.
        if (ArgAfter(Environment.GetCommandLineArgs(), "--subject") is { } sid &&
            window.ViewModel.Subjects.FirstOrDefault(x => x.Id == sid) is { } subject)
        {
            window.ViewModel.ShowSubjects = true;
            window.ViewModel.SelectedSubject = subject;
            if (ArgAfter(Environment.GetCommandLineArgs(), "--correction") is { } cid &&
                subject.Corrections.FirstOrDefault(c => c.Id == cid) is { } correction)
                window.ViewModel.SelectedCorrection = correction;
            if (Environment.GetCommandLineArgs().Contains("--trace")) window.ViewModel.OpenTraceForCorrectionCommand.Execute(null);
        }
        if (Environment.GetCommandLineArgs().Contains("--points")) window.ViewModel.ShowPointsTabCommand.Execute(null);
        if (Environment.GetCommandLineArgs().Contains("--ratios")) window.ViewModel.ShowRatios = true;   // onglet Ratios du bilan
        // --layers SNH,SH,SBH : seuls ces calques visibles (revue visuelle des couleurs, Évolution 4.2)
        if (ArgAfter(Environment.GetCommandLineArgs(), "--layers")?.Split(',') is { } codes)
            foreach (var layer in window.ViewModel.Layers) layer.IsVisible = codes.Contains(layer.Code);
        // --spaces : onglet Espaces d'un projet généré, premier espace sélectionné (revue visuelle, Évolution 4.0)
        if (Environment.GetCommandLineArgs().Contains("--spaces"))
        {
            window.ViewModel.ShowSpacesTabCommand.Execute(null);
            window.ViewModel.SelectedSpace = window.ViewModel.SpacesView.Cast<ViewModels.SpaceItem>().FirstOrDefault();
            if (Environment.GetCommandLineArgs().Contains("--context")) window.ViewModel.ShowIfcContext = true;
        }
        if (Environment.GetCommandLineArgs().Contains("--report")) window.ViewModel.ShowAiReportCommand.Execute(null);
        if (Environment.GetCommandLineArgs().Contains("--ai-panel")) window.ViewModel.OpenAiPanelCommand.Execute(null);
        if (capture is not null) await CaptureAsync(window, capture);
    }

    private static async Task CaptureAsync(Window window, string path)
    {
        await Task.Delay(TimeSpan.FromSeconds(2));   // animation de caméra et rendu terminés
        var dpi = System.Windows.Media.VisualTreeHelper.GetDpi(window);
        var bmp = new System.Windows.Media.Imaging.RenderTargetBitmap(
            (int)(window.ActualWidth * dpi.DpiScaleX), (int)(window.ActualHeight * dpi.DpiScaleY),
            dpi.PixelsPerInchX, dpi.PixelsPerInchY, System.Windows.Media.PixelFormats.Pbgra32);
        bmp.Render(window);
        var png = new System.Windows.Media.Imaging.PngBitmapEncoder();
        png.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
        await using (var f = File.Create(path)) png.Save(f);
        window.Close();
    }

    public static void ApplyTheme(string theme)
    {
        var dark = theme != "Light";
        var dicts = Current.Resources.MergedDictionaries;
        dicts[ColorsDictionaryIndex] = new ResourceDictionary
        {
            Source = new Uri($"Themes/Colors.{(dark ? "Dark" : "Light")}.xaml", UriKind.Relative),
        };
        ApplicationThemeManager.Apply(dark ? ApplicationTheme.Dark : ApplicationTheme.Light);
        // Accent Fluent = token Accent du plan (pervenche), pas le bleu système. Les quatre teintes sont
        // imposées : la surcharge « thème » éclaircit l'accent en sombre jusqu'à le rendre presque blanc.
        var accent = (System.Windows.Media.Color)Current.Resources["ColorAccent"];
        ApplicationAccentColorManager.Apply(accent, accent, accent, accent);
    }
}
