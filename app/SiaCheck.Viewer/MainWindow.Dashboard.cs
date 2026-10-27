using System.IO;
using Microsoft.Web.WebView2.Core;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer;

/// <summary>
/// Écran Dashboard : la page web du dépôt (dashboard/, copiée à côté de l'exécutable) dans WebView2. La page demande
/// ses données (« pret ») et la vue lui envoie benchmark.json ; sur un serveur, la même page lit ce fichier elle-même.
/// </summary>
public partial class MainWindow
{
    private const string DashboardHost = "benchmark.siacheck";
    private bool _dashboardReady;

    private async void OnDashboardChanged(string? property)
    {
        if (property is not (nameof(MainViewModel.IsDashboard) or nameof(MainViewModel.DashboardVersion)) || !ViewModel.IsDashboard)
            return;
        try
        {
            if (!_dashboardReady) await InitDashboardAsync();
            // Rechargée à chaque entrée et à chaque relecture de la base : données et thème à jour
            var mine = ViewModel.MyProjectJson is null ? "" : "&projet=mien";
            DashboardView.CoreWebView2.Navigate($"https://{DashboardHost}/index.html?theme={ViewModel.DashboardTheme}{mine}");
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
        core.SetVirtualHostNameToFolderMapping(DashboardHost, pages, CoreWebView2HostResourceAccessKind.Deny);
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.WebMessageReceived += (_, e) =>
        {
            if (e.TryGetWebMessageAsString() != "pret") return;
            var json = File.Exists(ViewModel.BenchmarkFile) ? File.ReadAllText(ViewModel.BenchmarkFile) : "{}";
            core.PostWebMessageAsString(json);
            if (ViewModel.MyProjectJson is { } mine) core.PostWebMessageAsString($"{{\"monProjet\":{mine}}}");
        };
        // Liens externes éventuels : jamais dans le cadre de l'application
        core.NewWindowRequested += (_, e) => e.Handled = true;
        _dashboardReady = true;
    }
}
