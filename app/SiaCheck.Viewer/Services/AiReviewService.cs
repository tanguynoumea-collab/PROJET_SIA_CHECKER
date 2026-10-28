using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Anthropic;
using Anthropic.Exceptions;
using Beta = Anthropic.Models.Beta.Messages;
using Msg = Anthropic.Models.Messages;

namespace SiaCheck.Viewer.Services;

/// <summary>Modèle, tarifs et estimation de coût de la revue IA (tarifs API Anthropic, USD par million de jetons).</summary>
public static class AiPricing
{
    public const string Model = "claude-opus-5-5";
    public const string ModelLabel = "Claude Opus 5.5";
    public const decimal InputPerMTok = 4m;
    public const decimal OutputPerMTok = 20m;
    /// <summary>Plafond de Claude Opus 5.5 en flux : la réflexion du modèle et le rapport (ratios compris) y tiennent.</summary>
    public const int MaxOutputTokens = 128000;

    /// <summary>
    /// Sortie attendue : ~4 000 jetons de rapport + ~1 500 de décisions sur les corrections + ~60 par verdict
    /// (L'Orée : 155 points, ~14 500 jetons), jusqu'à trois fois plus avec la réflexion du modèle, plafonnée à
    /// <see cref="MaxOutputTokens"/>.
    /// </summary>
    public static (long Min, long Max) OutputTokens(int issueCount)
    {
        var text = 5500L + 60L * issueCount;
        return (Math.Min(text, MaxOutputTokens), Math.Min(3 * text, MaxOutputTokens));
    }

    public static decimal Cost(long inputTokens, long outputTokens) =>
        (inputTokens * InputPerMTok + outputTokens * OutputPerMTok) / 1_000_000m;
}

public sealed record AiCostEstimate(long InputTokens, long MinOutputTokens, long MaxOutputTokens)
{
    public decimal MinUsd => AiPricing.Cost(InputTokens, MinOutputTokens);
    public decimal MaxUsd => AiPricing.Cost(InputTokens, MaxOutputTokens);
}

/// <summary>Prompt de la revue : procédure SKILL.md + exemple de rapport (système), preuves (utilisateur).</summary>
public sealed class AiReviewPrompt
{
    public required string System { get; init; }
    public required string User { get; init; }
    public required int IssueCount { get; init; }
    /// <summary>Sortie attendue (jetons) quand elle ne suit pas la revue de la Fiabilisation (analyse IA de la génération).</summary>
    public (long Min, long Max)? Output { get; init; }

    private static string Resource(string name)
    {
        using var s = typeof(AiReviewPrompt).Assembly.GetManifestResourceStream($"SiaCheck.Viewer.Prompts.{name}")
                      ?? throw new InvalidOperationException($"Ressource {name} absente de l'application.");
        using var r = new StreamReader(s, Encoding.UTF8);
        return r.ReadToEnd();
    }

    public static AiReviewPrompt Build(string projectName, string analysisDate, string reviewDate, string evidenceJson)
    {
        using var ev = JsonDocument.Parse(evidenceJson);
        var issueCount = ev.RootElement.TryGetProperty("issues", out var issues) ? issues.GetArrayLength() : 0;
        var system = $$"""
            Tu es la sur-vérification par IA de SIA Check Viewer, la visionneuse de contrôle des surfaces SIA 416
            produites par Treegram. Tu appliques la procédure de l'équipe reproduite dans <procedure>.

            Dans l'application, les étapes 1 (analyse) et 2 (preuves) sont déjà faites : le message de l'utilisateur
            contient le fichier de preuves JSON complet. Tu n'as ni outil, ni accès au dépôt, aux plans ou au modèle :
            appuie-toi uniquement sur ces preuves, et dis-le quand une conclusion demande une vérification dans Treegram.
            Fais les étapes 3 à 6. Vérifie chaque chiffre contre les preuves avant de l'écrire.

            <exemple_rapport> est un rapport réel d'un autre passage, donné pour sa forme et son niveau d'exigence :
            ne recopie aucun de ses constats, qui doivent tous venir des preuves fournies.

            Réponds exactement dans ce format, sans rien d'autre hors des trois balises :

            <rapport>
            (le rapport markdown complet de l'étape 5, titre compris)
            </rapport>
            <verdicts>
            {"<clé du point>": {"verdict_ia": "vrai sujet|à confirmer|faux positif|agrégat", "sujet": "S1" ou null, "raison": "une phrase chiffrée"}, …}
            </verdicts>
            <sujets>
            {"S1": {"titre": "…", "certitude": "vrai sujet|à confirmer|faux positif", "action": "corriger|aucune|à vérifier",
                    "explication": "…", "base": ["<id d'un sujet de propositions>"], "par_defaut": "garder|rejeter",
                    "decisions": [{"id": "<id d'une correction proposée>", "decision": "garder|modifier|rejeter|ajouter", "explication": "…"}]}, …}
            </sujets>

            Le bloc <verdicts> est un objet JSON valide qui contient chacune des {{issueCount}} clés de la liste
            `issues` des preuves, recopiées caractère pour caractère, et seulement elles. Le bloc <sujets> est un
            objet JSON valide au format de l'étape 6 de la procédure : il décide des corrections de `propositions`
            (identifiants recopiés tels quels), et chaque sujet S… cité dans <verdicts> y figure. Les métadonnées du
            fichier (projet, dates, modèle) sont ajoutées par l'application.

            <procedure>
            {{Resource("revue-ia.SKILL.md")}}
            </procedure>

            <exemple_rapport>
            {{Resource("revue-ia.exemple.md")}}
            </exemple_rapport>
            """;
        var user = $"""
            Projet : {projectName}
            Analyse sia-check du {analysisDate} · revue du {reviewDate} · {issueCount} points d'attention.

            <preuves>
            {evidenceJson}
            </preuves>
            """;
        return new AiReviewPrompt { System = system, User = user, IssueCount = issueCount };
    }
}

public sealed record AiStreamProgress(bool Writing, long Characters, TimeSpan Elapsed)
{
    /// <summary>Estimation grossière (≈ 3,5 caractères par jeton en français) : l'API ne compte qu'à la fin.</summary>
    public long ApproxTokens => (long)(Characters / 3.5);
}

public sealed record AiReviewResponse(string Text, long InputTokens, long OutputTokens, string? StopReason)
{
    public decimal CostUsd => AiPricing.Cost(InputTokens, OutputTokens);
}

/// <summary>Erreur à montrer telle quelle à l'utilisateur (clé refusée, quota, réponse inexploitable…).</summary>
public sealed class AiReviewException(string message, Exception? inner = null) : Exception(message, inner);

/// <summary>Appel de l'API Messages d'Anthropic (SDK officiel), en flux : réponses longues, annulables.</summary>
public sealed class AiReviewClient(string apiKey)
{
    private readonly AnthropicClient _client = new() { ApiKey = apiKey, Timeout = TimeSpan.FromMinutes(30) };

    public async Task<AiCostEstimate> EstimateAsync(AiReviewPrompt prompt, CancellationToken ct)
    {
        var count = await Guard(() => _client.Messages.CountTokens(new Msg.MessageCountTokensParams
        {
            Model = AiPricing.Model,
            System = prompt.System,
            Messages = [new Msg.UserMessageParam { Content = prompt.User }],
            Thinking = new Msg.ThinkingConfigAdaptive(),
        }, ct));
        var (min, max) = prompt.Output ?? AiPricing.OutputTokens(prompt.IssueCount);
        return new AiCostEstimate(count.InputTokens, min, max);
    }

    public Task<AiReviewResponse> RunAsync(AiReviewPrompt prompt, IProgress<AiStreamProgress>? progress, CancellationToken ct) =>
        Guard(async () =>
        {
            var p = new Beta.MessageCreateParams
            {
                Model = AiPricing.Model,
                MaxTokens = AiPricing.MaxOutputTokens,
                System = prompt.System,
                Messages = [new Beta.BetaUserMessageParam { Content = prompt.User }],
                Thinking = new Beta.BetaThinkingConfigAdaptive(),
                OutputConfig = new Beta.BetaOutputConfig { Effort = Beta.Effort.High },
                // Refus d'un classifieur de sécurité : l'API relance d'elle-même sur le modèle de repli recommandé.
                Betas = ["server-side-fallback-2026-07-01"],
                Fallbacks = new Beta.Default(),
            };
            var text = new StringBuilder();
            long input = 0, output = 0;
            string? stop = null;
            var clock = System.Diagnostics.Stopwatch.StartNew();
            var lastReport = TimeSpan.Zero;
            await foreach (var e in _client.Beta.Messages.CreateStreaming(p, ct).WithCancellation(ct))
            {
                if (e.TryPickStart(out var start))
                    input = start.Message.Usage.InputTokens;
                else if (e.TryPickContentBlockDelta(out var delta) && delta.Delta.TryPickText(out var t))
                    text.Append(t.Text);
                else if (e.TryPickDelta(out var md))
                {
                    output = md.Usage.OutputTokens;
                    stop = md.Delta.StopReason?.Raw();
                }
                if (clock.Elapsed - lastReport > TimeSpan.FromMilliseconds(250))
                {
                    lastReport = clock.Elapsed;
                    progress?.Report(new AiStreamProgress(text.Length > 0, text.Length, clock.Elapsed));
                }
            }
            return new AiReviewResponse(text.ToString(), input, output, stop);
        });

    private static async Task<T> Guard<T>(Func<Task<T>> call)
    {
        try { return await call(); }
        catch (AnthropicUnauthorizedException ex) { throw new AiReviewException("Clé API refusée par Anthropic. Vérifiez-la ou saisissez-en une autre.", ex); }
        catch (AnthropicForbiddenException ex) { throw new AiReviewException("Cette clé API n'a pas accès au modèle " + AiPricing.ModelLabel + ".", ex); }
        catch (AnthropicRateLimitException ex) { throw new AiReviewException("Limite d'utilisation de l'API atteinte. Réessayez dans quelques minutes.", ex); }
        catch (AnthropicBadRequestException ex) when (ex.Message.Contains("anthropic-workspace-id", StringComparison.Ordinal))
        {
            throw new AiReviewException("Cette clé API n'est rattachée à aucun espace de travail (workspace). Dans la console Anthropic, " +
                                        "créez une clé dans un espace de travail (Settings → Workspaces), puis « Remplacer » la clé ici.", ex);
        }
        catch (AnthropicBadRequestException ex) { throw new AiReviewException($"Requête refusée par l'API : {ex.Message}", ex); }
        catch (Anthropic5xxException ex) { throw new AiReviewException("Service Anthropic indisponible. Réessayez plus tard.", ex); }
        catch (AnthropicIOException ex) { throw new AiReviewException($"Connexion à l'API Anthropic impossible : {ex.Message}", ex); }
        catch (AnthropicException ex) { throw new AiReviewException($"Erreur de l'API Anthropic : {ex.Message}", ex); }
    }
}

/// <summary>Résultat exploitable de la réponse du modèle.</summary>
public sealed record AiReviewOutput(string ReportMarkdown, Dictionary<string, AiVerdict> Points,
                                    IReadOnlyList<string> MissingKeys, IReadOnlyList<string> UnknownKeys,
                                    JsonObject? Subjects = null);

public static class AiReviewParser
{
    private const string MissingReason = "Point non traité par la revue IA : à examiner.";

    /// <summary>
    /// Extrait le rapport et les verdicts. Chaque point de l'analyse reçoit un verdict : un point oublié par
    /// le modèle passe « à confirmer » (et est signalé), une clé inventée est écartée.
    /// </summary>
    public static AiReviewOutput Parse(string text, IReadOnlyCollection<string> issueKeys)
    {
        var report = Between(text, "rapport")
                     ?? throw new AiReviewException("Réponse du modèle sans rapport (balise <rapport> absente).");
        var json = Between(text, "verdicts")
                   ?? throw new AiReviewException("Réponse du modèle sans verdicts (balise <verdicts> absente).");
        json = Unfence(json);
        Dictionary<string, AiVerdict> raw;
        try { raw = JsonSerializer.Deserialize<Dictionary<string, AiVerdict>>(json) ?? []; }
        catch (JsonException ex) { throw new AiReviewException($"Verdicts illisibles : {ex.Message}", ex); }

        var known = issueKeys.ToHashSet();
        var points = new Dictionary<string, AiVerdict>();
        foreach (var (key, v) in raw.Where(kv => known.Contains(kv.Key)))
        {
            var kind = v.Kind == AiVerdictKind.Unknown ? AiVerdictKind.ToConfirm : v.Kind;
            points[key] = new AiVerdict
            {
                Verdict = AiVerdict.Label(kind),
                Subject = string.IsNullOrWhiteSpace(v.Subject) ? null : v.Subject.Trim(),
                Reason = v.Reason.Trim(),
            };
        }
        var missing = issueKeys.Where(k => !points.ContainsKey(k)).ToList();
        foreach (var k in missing)
            points[k] = new AiVerdict { Verdict = AiVerdict.Label(AiVerdictKind.ToConfirm), Reason = MissingReason };
        return new AiReviewOutput(report.Trim() + "\n", points, missing, raw.Keys.Where(k => !known.Contains(k)).ToList(),
                                  ParseSubjects(text));
    }

    /// <summary>
    /// Bloc &lt;sujets&gt; (facultatif : une réponse au format v1 n'en a pas). Il est gardé tel quel ; le moteur
    /// le valide décision par décision (<c>sia-check --revue</c>).
    /// </summary>
    private static JsonObject? ParseSubjects(string text)
    {
        var json = Between(text, "sujets");
        if (json is null) return null;
        try
        {
            return JsonNode.Parse(Unfence(json)) as JsonObject
                   ?? throw new AiReviewException("Sujets illisibles : objet JSON attendu.");
        }
        catch (JsonException ex) { throw new AiReviewException($"Sujets illisibles : {ex.Message}", ex); }
    }

    private static string Unfence(string json)
    {
        json = json.Trim();
        if (json.StartsWith("```"))   // bloc de code markdown autour du JSON
            json = json[(json.IndexOf('\n') + 1)..json.LastIndexOf("```", StringComparison.Ordinal)];
        return json;
    }

    private static string? Between(string text, string tag)
    {
        var open = text.IndexOf($"<{tag}>", StringComparison.Ordinal);
        if (open < 0) return null;
        open += tag.Length + 2;
        var close = text.IndexOf($"</{tag}>", open, StringComparison.Ordinal);
        return close < 0 ? null : text[open..close];
    }
}
