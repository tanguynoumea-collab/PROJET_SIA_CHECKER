using System.IO;
using System.Windows.Threading;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>
/// Aperçu en direct du bilan par niveau et des ratios : à chaque décision sur les corrections, le moteur réapplique
/// le journal aux surfaces gardées par la dernière analyse (sia-check --apercu, quelques secondes) ; le bilan et les
/// ratios montrent ce résultat jusqu'à la prochaine analyse complète. Sans décision en attente, ceux de l'analyse.
/// </summary>
public sealed partial class MainViewModel
{
    private static readonly TimeSpan PreviewDelay = TimeSpan.FromMilliseconds(600);
    private BalancePreview? _balancePreview;
    private DispatcherTimer? _previewTimer;
    private CancellationTokenSource? _previewCts;

    private IReadOnlyList<LevelBalance> BalanceLevels => _balancePreview?.Levels ?? Document?.Levels ?? [];
    private IReadOnlyList<Ratio> BalanceRatios => _balancePreview?.Ratios ?? Document?.Ratios ?? [];

    public bool IsBalancePreview => _balancePreview is not null;
    public string BalancePreviewText => IsBalancePreviewRunning ? "aperçu en calcul…" : "aperçu avec corrections";
    private bool IsBalancePreviewRunning => _previewCts is not null;

    /// <summary>Décision prise : recalcul après un court délai (plusieurs décisions de suite = un seul calcul).</summary>
    private void ScheduleBalancePreview()
    {
        if (_engine is null || ProjectDir is null || Document is null) return;
        if (PendingCorrections == 0) { ClearBalancePreview(); return; }
        _previewTimer ??= new DispatcherTimer { Interval = PreviewDelay };
        _previewTimer.Tick -= OnPreviewTimer;
        _previewTimer.Tick += OnPreviewTimer;
        _previewTimer.Stop();
        _previewTimer.Start();
    }

    private async void OnPreviewTimer(object? sender, EventArgs e)
    {
        _previewTimer?.Stop();
        await RunBalancePreviewAsync();
    }

    private async Task RunBalancePreviewAsync()
    {
        if (_engine is null || ProjectDir is null || IsAnalysing) return;
        var dir = ProjectDir;
        var journal = _paths.CorrectionsFile(dir);
        var cache = _paths.SurfacesCacheFile(dir);
        if (!File.Exists(journal)) return;
        _previewCts?.Cancel();
        var cts = _previewCts = new CancellationTokenSource();
        OnPropertyChanged(nameof(BalancePreviewText));
        var output = _paths.PreviewFile(dir);
        try
        {
            // Surfaces gardées par une analyse : quelques secondes ; sinon (analyse antérieure) le projet est relu une fois.
            var run = File.Exists(cache) ? await _engine.PreviewAsync(cache, journal, output, cts.Token)
                : await _engine.PreviewFromProjectAsync(dir, cache, journal, output, cts.Token);
            if (cts.IsCancellationRequested || dir != ProjectDir || !run.Succeeded || !File.Exists(output)) return;
            _balancePreview = System.Text.Json.JsonSerializer.Deserialize<BalancePreview>(await File.ReadAllTextAsync(output));
            OnPropertyChanged(nameof(IsBalancePreview));
            FillBalance();
        }
        catch (OperationCanceledException) { /* une décision plus récente relance le calcul */ }
        catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException or System.ComponentModel.Win32Exception)
        {
            _balancePreview = null;   // l'aperçu n'est qu'un confort : le bilan de l'analyse reste affiché
        }
        finally
        {
            if (_previewCts == cts) { _previewCts = null; cts.Dispose(); }
            OnPropertyChanged(nameof(BalancePreviewText));
        }
    }

    /// <summary>Nouvelle analyse, ou plus rien en attente : le bilan et les ratios de l'analyse font foi.</summary>
    private void ClearBalancePreview()
    {
        _previewTimer?.Stop();
        _previewCts?.Cancel();
        if (_balancePreview is null) return;
        _balancePreview = null;
        OnPropertyChanged(nameof(IsBalancePreview));
        FillBalance();
    }
}
