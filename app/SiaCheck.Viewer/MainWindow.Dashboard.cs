using System.IO;
using Microsoft.Web.WebView2.Core;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer;

/// <summary>
/// Écran Dashboard : la page web du dépôt (dashboard/, copiée à côté de l'exécutable) dans WebView2. La page demande
/// ses données (« pret ») et la vue lui envoie benchmark.json ; sur un serveur, la même page lit ce fichier elle-même.
/// Les maquettes 3D web (MAQ-*.json.gz) sont lues dans le dossier de la base sur un hôte à part (https://maquettes.siacheck/),
/// que seul WebResourceRequested sert : un chemin de l'hôte du dashboard serait servi par son dossier (fichier
/// introuvable), sans passer par le gestionnaire. Aucun autre fichier du dossier de la base n'est servi.
/// </summary>
public partial class MainWindow
{
    private const string DashboardHost = "benchmark.siacheck";
    private const string ModelsHost = "maquettes.siacheck";
    private const string Crlf = "\r\n";   // séparateur des en-têtes HTTP
    private bool _dashboardReady;

    private async void OnDashboardChanged(string? property)
    {
        if (property is not (nameof(MainViewModel.IsDashboard) or nameof(MainViewModel.DashboardVersion) or nameof(MainViewModel.DashboardTheme)) || !ViewModel.IsDashboard)
            return;
        try
        {
            if (!_dashboardReady) await InitDashboardAsync();
            // Rechargée à chaque entrée et à chaque relecture de la base : données et thème à jour
            var mine = ViewModel.MyProjectJson is null ? "" : "&projet=mien";
            var module = ViewModel.DashboardModule.Length > 0 ? $"&module={ViewModel.DashboardModule}" : "";     // module Données SIG
            DashboardView.CoreWebView2.Navigate($"https://{DashboardHost}/index.html?theme={ViewModel.DashboardTheme}&maquettes=https://{ModelsHost}/{mine}{module}");
        }
        catch (WebView2RuntimeNotFoundException)
        {
            ViewModel.DashboardError = "Le composant Microsoft Edge WebView2 est requis pour afficher le dashboard. " +
                                       "Installez-le depuis https://developer.microsoft.com/microsoft-edge/webview2/, puis relancez SIA Check.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            ViewModel.DashboardError = $"Le dashboard ne peut pas s'afficher : {ex.Message}";
        }
    }

    private async Task InitDashboardAsync()
    {
        var pages = Path.Combine(AppContext.BaseDirectory, "dashboard");
        if (!File.Exists(Path.Combine(pages, "index.html")))
            throw new IOException($"pages du dashboard introuvables ({pages}) : réinstallez l'application.");
        var env = await CoreWebView2Environment.CreateAsync(null, _paths.WebViewDataDir);
        await DashboardView.EnsureCoreWebView2Async(env);
        var core = DashboardView.CoreWebView2;
        // Pages à jour après une mise à jour de l'application : le cache disque (scripts, styles) est vidé à l'ouverture.
        // Le stockage local de la page (sélection, réglages de la carte) n'est pas touché.
        await core.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.DiskCache);
        core.SetVirtualHostNameToFolderMapping(DashboardHost, pages, CoreWebView2HostResourceAccessKind.Deny);
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.WebMessageReceived += (_, e) =>
        {
            var message = e.TryGetWebMessageAsString();
            // la page passe du benchmark au module Données SIG ou l'inverse : le titre suit, sans recharger
            if (message.StartsWith("module:", StringComparison.Ordinal)) { ViewModel.ShowDashboardModule(message["module:".Length..]); return; }
            if (message != "pret") return;
            var json = File.Exists(ViewModel.BenchmarkFile) ? File.ReadAllText(ViewModel.BenchmarkFile) : "{}";
            core.PostWebMessageAsString(json);
            if (ViewModel.MyProjectJson is { } mine) core.PostWebMessageAsString($"{{\"monProjet\":{mine}}}");
        };
        core.AddWebResourceRequestedFilter($"https://{ModelsHost}/*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += (_, e) => e.Response = BaseModelResponse(core.Environment, e.Request.Uri);
        core.DownloadStarting += OnDashboardDownload;
        // Liens externes éventuels : jamais dans le cadre de l'application
        core.NewWindowRequested += (_, e) => e.Handled = true;
        _dashboardReady = true;
    }

    /// <summary>
    /// Export Excel de la page (Programmer, docs/V5_PLAN.md partie 4) : l'utilisateur choisit où enregistrer, sans la
    /// barre de téléchargement du navigateur. Le dialogue s'ouvre hors de l'événement (report), comme le veut WebView2.
    /// </summary>
    private void OnDashboardDownload(object? sender, CoreWebView2DownloadStartingEventArgs e)
    {
        var deferral = e.GetDeferral();
        Dispatcher.BeginInvoke(() =>
        {
            using (deferral)
            {
                var name = Path.GetFileName(e.ResultFilePath);
                var dialog = new Microsoft.Win32.SaveFileDialog
                {
                    FileName = name,
                    DefaultExt = Path.GetExtension(name),
                    Filter = Path.GetExtension(name).Equals(".xlsx", StringComparison.OrdinalIgnoreCase)
                        ? "Classeur Excel (*.xlsx)|*.xlsx" : "Tous les fichiers (*.*)|*.*",
                    InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                };
                if (dialog.ShowDialog(this) != true) { e.Cancel = true; return; }
                e.ResultFilePath = dialog.FileName;
                e.Handled = true;     // pas de barre de téléchargement
            }
        });
    }

    /// <summary>Une maquette de la base (nom MAQ-*.json.gz seulement, sans chemin), ou 404.</summary>
    private CoreWebView2WebResourceResponse BaseModelResponse(CoreWebView2Environment env, string uri)
    {
        var name = Uri.UnescapeDataString(new Uri(uri).AbsolutePath.TrimStart('/'));
        var path = ViewModel.HasBenchmarkFolder && Services.WebModel.IsModelFile(name) ? Path.Combine(ViewModel.BenchmarkFolder, name) : null;
        // la page (autre hôte) lit la réponse : en-tête CORS pour elle seule
        var cors = $"Access-Control-Allow-Origin: https://{DashboardHost}";
        if (path is null || !File.Exists(path)) return env.CreateWebResourceResponse(null, 404, "Not Found", cors);
        try
        {
            var bytes = File.ReadAllBytes(path);
            return env.CreateWebResourceResponse(new MemoryStream(bytes), 200, "OK",
                $"Content-Type: application/gzip{Crlf}Cache-Control: no-store{Crlf}{cors}");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return env.CreateWebResourceResponse(null, 503, "Unavailable", cors);
        }
    }
}
