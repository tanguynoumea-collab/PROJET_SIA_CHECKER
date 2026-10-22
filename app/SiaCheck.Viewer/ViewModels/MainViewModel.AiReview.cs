using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.ViewModels;

/// <summary>Étapes de la revue IA lancée depuis l'app (plan, Évolution 1.1).</summary>
public enum AiStage { Idle, Analysing, Estimating, AwaitingConfirm, Writing, Done }

/// <summary>
/// Sur-vérification par IA : verdicts de la dernière revue (liste, filtre, carte Détail, rapport) et
/// revue complète lancée depuis l'app (sia-check + preuves → API Messages → rapport et verdicts).
/// </summary>
public sealed partial class MainViewModel
{
    private ApiKeyStore? _keys;
    private ApiKeyStore Keys => _keys ??= new ApiKeyStore(_paths.ApiKeyFile);
    private TaskCompletionSource<bool>? _aiConfirm;
    private CancellationTokenSource? _aiCts;

    /// <summary>Point de départ de la recherche de <c>docs/revue-ia</c> (copie de travail du dépôt).</summary>
    internal string AiSearchBaseDir { get; set; } = AppContext.BaseDirectory;

    // ------------------------------------------------------------------ verdicts chargés

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasAiReview), nameof(AiSummary), nameof(HasAiReport), nameof(AiReportTitle))]
    private AiReview? _aiReview;

    public bool HasAiReview => AiReview is not null;
    public bool HasAiReport => AiReview?.ReportPath is not null;

    /// <summary>« IA 22.10 · 3 sujets » (vrais sujets) : lien de la barre de commande vers le rapport.</summary>
    public string AiSummary
    {
        get
        {
            if (AiReview is null) return "";
            var date = DateTime.TryParse(AiReview.Data.ReviewDate, out var d) ? d.ToString("dd.MM") : AiReview.Data.ReviewDate;
            var subjects = AiReview.Data.Points.Values.Where(v => v.Kind == AiVerdictKind.TrueIssue)
                .Select(v => v.Subject).Where(s => s is not null).Distinct().Count();
            return $"IA {date} · {subjects} sujet{(subjects > 1 ? "s" : "")}";
        }
    }

    public string AiReportTitle => AiReview is null ? "" :
        $"Revue IA — {AiReview.Data.Project} · {AiReview.Data.ReviewDate} · {AiReview.Data.Model}";

    public IReadOnlyList<ChoiceItem> AiChoices { get; } =
    [
        new("Tous les verdicts IA", ""), new("Vrais sujets", "true"), new("À confirmer", "confirm"),
        new("Faux positifs", "false"), new("Agrégats", "aggregate"), new("Sans verdict", "none"),
    ];

    [ObservableProperty] private string _aiFilter = "";
    [ObservableProperty] private int _aiFalsePositiveCount;

    partial void OnAiFilterChanged(string value) => RefreshIssues();

    private bool MatchesAi(IssueItem i) => AiFilter switch
    {
        "true" => i.AiKind == AiVerdictKind.TrueIssue,
        "confirm" => i.AiKind == AiVerdictKind.ToConfirm,
        "false" => i.AiKind == AiVerdictKind.FalsePositive,
        "aggregate" => i.AiKind == AiVerdictKind.Aggregate,
        "none" => !i.HasAi,
        _ => true,
    };

    /// <summary>Dernière revue du projet : dossier de l'app, sinon <c>docs/revue-ia</c> du dépôt.</summary>
    private void LoadAiReview(ViewerDocument doc)
    {
        var review = AiReviewFiles.FindLatest(doc.Project,
            AiReviewFiles.SearchDirs(_paths.AiReviewDir(ProjectDir!), AiSearchBaseDir));
        ApplyAiReview(review);
    }

    private void ApplyAiReview(AiReview? review)
    {
        AiReview = review;
        foreach (var i in Issues) i.Ai = review?.Get(i.Key);
        UpdateAiCounts();
        if (review is null) AiFilter = "";
        AiReportMarkdown = null;
        IsAiReportOpen = false;
    }

    private void UpdateAiCounts() =>
        AiFalsePositiveCount = Issues.Count(i => i is { AiKind: AiVerdictKind.FalsePositive, IsResolved: false, Status: ReviewStatus.ToReview });

    /// <summary>
    /// Passe en « Faux positif » les points que l'IA juge faux positifs et que personne n'a encore statués.
    /// La raison de l'IA devient le commentaire quand il est vide : le statut reste traçable.
    /// </summary>
    [RelayCommand]
    private void ApplyAiFalsePositives()
    {
        var targets = Issues.Where(i => i is { AiKind: AiVerdictKind.FalsePositive, IsResolved: false, Status: ReviewStatus.ToReview }).ToList();
        foreach (var i in targets)
        {
            if (string.IsNullOrWhiteSpace(i.Comment)) i.Comment = $"Revue IA : {i.AiReason}";
            i.Status = ReviewStatus.FalsePositive;   // enregistré par Track()
        }
        _commentSave.Stop();
        UpdateAiCounts();
        _shell.Notify(targets.Count == 0 ? "Aucun point « À traiter » jugé faux positif par l'IA."
                                         : $"{targets.Count} points passés en « Faux positif » (raison de l'IA en commentaire).");
    }

    // ------------------------------------------------------------------ rapport

    [ObservableProperty] private bool _isAiReportOpen;
    [ObservableProperty] private string? _aiReportMarkdown;

    [RelayCommand]
    private void ShowAiReport()
    {
        if (AiReview?.ReportPath is not { } path) return;
        try
        {
            AiReportMarkdown = File.ReadAllText(path);
            IsAiReportOpen = true;
        }
        catch (IOException ex) { _shell.Notify($"Rapport illisible : {ex.Message}", isError: true); }
    }

    [RelayCommand]
    private void CloseAiReport() => IsAiReportOpen = false;

    [RelayCommand]
    private void OpenAiReportFile()
    {
        if (AiReview?.ReportPath is { } path) _shell.OpenFile(path);
    }

    // ------------------------------------------------------------------ clé API

    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasApiKey), nameof(CanStartAiReview))] private string? _apiKeyMasked;
    [ObservableProperty] private bool _isReplacingKey;
    public bool HasApiKey => ApiKeyMasked is not null;

    private void RefreshKey() => ApiKeyMasked = Keys.Load() is { } k ? ApiKeyStore.Mask(k) : null;

    [RelayCommand]
    private void SaveApiKey(string? key)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        try
        {
            Keys.Save(key);
            IsReplacingKey = false;
            RefreshKey();
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or System.Security.Cryptography.CryptographicException)
        {
            AiError = ex.Message;
        }
    }

    [RelayCommand]
    private void ForgetApiKey()
    {
        Keys.Clear();
        RefreshKey();
    }

    [RelayCommand]
    private void ReplaceApiKey() => IsReplacingKey = true;

    // ------------------------------------------------------------------ revue complète depuis l'app

    [ObservableProperty] private bool _isAiPanelOpen;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsAiRunning), nameof(IsAwaitingConfirm), nameof(CanStartAiReview), nameof(IsAiWriting),
                              nameof(IsAiIdle), nameof(AiAnalysisDone), nameof(AiEstimateDone))]
    private AiStage _aiStage;
    [ObservableProperty] private string _aiStepAnalysis = "";
    [ObservableProperty] private string _aiStepEvidence = "";
    [ObservableProperty] private string _aiStepEstimate = "";
    [ObservableProperty] private string _aiStepWriting = "";
    [ObservableProperty] private double _aiProgress;
    [ObservableProperty] private bool _aiProgressKnown;
    [ObservableProperty] private AiCostEstimate? _aiEstimate;
    [ObservableProperty] private string? _aiCostText;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(HasAiError))] private string? _aiError;

    public bool HasAiError => !string.IsNullOrEmpty(AiError);
    public bool IsAiRunning => AiStage is not (AiStage.Idle or AiStage.Done);
    public bool IsAwaitingConfirm => AiStage == AiStage.AwaitingConfirm;
    public bool IsAiWriting => AiStage == AiStage.Writing;
    public bool IsAiIdle => !IsAiRunning;
    public bool AiAnalysisDone => AiStage > AiStage.Analysing;
    public bool AiEstimateDone => AiStage > AiStage.Estimating;
    public bool CanStartAiReview => HasApiKey && !IsAiRunning && _engine is not null && ProjectDir is not null;
    public string AiModelLabel => AiPricing.ModelLabel;

    [RelayCommand]
    private void OpenAiPanel()
    {
        RefreshKey();
        IsReplacingKey = !HasApiKey;
        if (!IsAiRunning) { AiError = null; AiStage = AiStage.Idle; ResetAiSteps(); }
        IsAiPanelOpen = true;
    }

    [RelayCommand]
    private void CloseAiPanel()
    {
        if (IsAiRunning) _aiCts?.Cancel();
        IsAiPanelOpen = false;
    }

    [RelayCommand]
    private void ConfirmAiReview() => _aiConfirm?.TrySetResult(true);

    [RelayCommand]
    private void CancelAiReview() => _aiCts?.Cancel();

    private void ResetAiSteps()
    {
        AiStepAnalysis = AiStepEvidence = AiStepEstimate = AiStepWriting = "";
        AiEstimate = null;
        AiCostText = null;
        AiProgress = 0;
        AiProgressKnown = false;
    }

    [RelayCommand]
    private async Task StartAiReviewAsync()
    {
        if (!CanStartAiReview || IsAnalysing) return;
        var key = Keys.Load();
        if (key is null) { RefreshKey(); AiError = "Clé API illisible : saisissez-la de nouveau."; return; }
        AiError = null;
        ResetAiSteps();
        _aiCts = new CancellationTokenSource();
        var ct = _aiCts.Token;
        var dir = ProjectDir!;
        var reviewDate = DateTime.Now.ToString("yyyy-MM-dd");
        try
        {
            // 1-2. Analyse fraîche + preuves, en une exécution du moteur.
            AiStage = AiStage.Analysing;
            var json = _paths.AnalysisFile(dir);
            var tmp = json + ".new";
            var evidencePath = Path.Combine(Path.GetDirectoryName(json)!, $"{AppPaths.Slug(dir)}.preuves.json");
            Directory.CreateDirectory(Path.GetDirectoryName(json)!);
            var progress = new Progress<AnalysisProgress>(p =>
            {
                if (p.Step < p.StepCount) AiStepAnalysis = $"étape {p.Step}/{p.StepCount - 1} : {p.Label}";
                else { AiStepAnalysis = "terminée"; AiStepEvidence = "calcul…"; }
            });
            var run = await _engine!.AnalyseWithEvidenceAsync(dir, tmp, evidencePath, progress, ct);
            LastLogFile = _paths.LogFile(dir);
            await File.WriteAllTextAsync(LastLogFile, run.Log, ct);
            if (!run.Succeeded || !File.Exists(tmp) || !File.Exists(evidencePath))
                throw new AiReviewException(run.ErrorMessage ?? $"Le moteur s'est arrêté avec le code {run.ExitCode}.");
            File.Move(tmp, json, overwrite: true);
            Load(ViewerDocument.Load(json));
            var doc = Document!;
            AiStepAnalysis = $"{doc.Surfaces.Count:N0} surfaces · {doc.Issues.Count} points";
            var evidence = await File.ReadAllTextAsync(evidencePath, ct);
            AiStepEvidence = EvidenceSummary(evidence);

            // 3. Estimation du coût (comptage exact des jetons envoyés), puis feu vert de l'utilisateur.
            AiStage = AiStage.Estimating;
            AiStepEstimate = "comptage des jetons…";
            var prompt = AiReviewPrompt.Build(doc.Project, doc.Date, reviewDate, evidence);
            var client = new AiReviewClient(key);
            var estimate = AiEstimate = await client.EstimateAsync(prompt, ct);
            AiStepEstimate = $"{estimate.InputTokens:N0} jetons envoyés";
            AiCostText = $"Coût estimé : {estimate.MinUsd:0.00} – {estimate.MaxUsd:0.00} USD";
            AiStage = AiStage.AwaitingConfirm;
            _aiConfirm = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using (ct.Register(() => _aiConfirm.TrySetCanceled(ct))) await _aiConfirm.Task;

            // 4. Rédaction par le modèle, en flux.
            AiStage = AiStage.Writing;
            AiStepWriting = "réflexion du modèle…";
            var expected = Math.Max(estimate.MinOutputTokens, 1);
            var stream = new Progress<AiStreamProgress>(p =>
            {
                var t = $"{(int)p.Elapsed.TotalMinutes} min {p.Elapsed.Seconds:00} s";
                AiProgressKnown = p.Writing;
                AiProgress = Math.Min(0.98, (double)p.ApproxTokens / expected);
                AiStepWriting = p.Writing ? $"~{p.ApproxTokens:N0} / ~{expected:N0} jetons · {t}" : $"réflexion du modèle… {t}";
            });
            var response = await client.RunAsync(prompt, stream, ct);
            if (response.StopReason == "max_tokens")
                throw new AiReviewException($"Réponse tronquée à {AiPricing.MaxOutputTokens:N0} jetons : relancez la revue.");
            if (response.StopReason == "refusal")
                throw new AiReviewException("Le modèle a décliné la demande (filtre de sécurité). Relancez la revue ; si cela persiste, signalez-le.");
            var output = AiReviewParser.Parse(response.Text, doc.Issues.Select(i => i.Key).ToList());

            // 5-6. Rapport et verdicts au format de docs/revue-ia, à côté des preuves.
            var saveDir = _paths.AiReviewDir(dir);
            var review = AiReviewFiles.Save(saveDir, doc.Project, reviewDate, output.ReportMarkdown, new AiVerdictFile
            {
                Project = doc.Project, AnalysisDate = doc.Date, ReviewDate = reviewDate,
                Model = $"{AiPricing.ModelLabel} (SIA Check Viewer)", Points = output.Points,
            });
            File.Copy(evidencePath, Path.Combine(saveDir, $"{AiReviewFiles.Prefix(doc.Project)}_{reviewDate}.preuves.json"), overwrite: true);
            AiStage = AiStage.Done;
            ApplyAiReview(review);
            IsAiPanelOpen = false;
            ShowAiReport();
            var missing = output.MissingKeys.Count > 0 ? $" · {output.MissingKeys.Count} points sans verdict du modèle (« à confirmer »)" : "";
            _shell.Notify($"Revue IA terminée · coût réel {response.CostUsd:0.00} USD ({response.InputTokens:N0} + {response.OutputTokens:N0} jetons){missing}.");
        }
        catch (OperationCanceledException)
        {
            AiStage = AiStage.Idle;
            ResetAiSteps();
            _shell.Notify("Revue IA annulée.");
        }
        catch (Exception ex) when (ex is AiReviewException or IOException or InvalidDataException
                                       or System.Text.Json.JsonException or System.ComponentModel.Win32Exception)
        {
            AiStage = AiStage.Idle;
            AiError = ex.Message;
        }
        finally
        {
            _aiConfirm = null;
            _aiCts.Dispose();
            _aiCts = null;
            OnPropertyChanged(nameof(CanStartAiReview));
        }
    }

    private static string EvidenceSummary(string evidenceJson)
    {
        using var ev = System.Text.Json.JsonDocument.Parse(evidenceJson);
        int Count(string name) => ev.RootElement.TryGetProperty(name, out var a) ? a.GetArrayLength() : 0;
        return $"{Count("levels")} niveaux · {Count("sep_decomposition")} SEP · {Count("interior_overlaps")} recouvrements";
    }
}
