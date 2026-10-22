using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Clé API Anthropic de l'utilisateur, chiffrée avec DPAPI (portée utilisateur courant) :
/// seul ce compte Windows, sur ce poste, peut la relire. Jamais écrite en clair, jamais dans le dépôt.
/// </summary>
public sealed class ApiKeyStore(string path)
{
    // Entropie propre à l'application : un autre programme du même utilisateur ne déchiffre pas le fichier par hasard.
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("SiaCheckViewer/anthropic-api-key/v1");

    public string Path { get; } = path;

    public bool HasKey => File.Exists(Path);

    public void Save(string key)
    {
        key = key.Trim();
        if (key.Length == 0 || key.Any(char.IsWhiteSpace))
            throw new ArgumentException("Clé API vide ou contenant des espaces.", nameof(key));
        var cipher = ProtectedData.Protect(Encoding.UTF8.GetBytes(key), Entropy, DataProtectionScope.CurrentUser);
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path)!);
        var tmp = Path + ".tmp";
        File.WriteAllBytes(tmp, cipher);
        File.Move(tmp, Path, overwrite: true);
    }

    /// <summary>Clé en clair, ou null si absente ou illisible (autre compte, autre poste, fichier abîmé).</summary>
    public string? Load()
    {
        try
        {
            if (!File.Exists(Path)) return null;
            var plain = ProtectedData.Unprotect(File.ReadAllBytes(Path), Entropy, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch (Exception ex) when (ex is CryptographicException or IOException)
        {
            return null;
        }
    }

    public void Clear()
    {
        if (File.Exists(Path)) File.Delete(Path);
    }

    /// <summary>« sk-ant-…x7Qa » : de quoi reconnaître sa clé sans l'afficher.</summary>
    public static string Mask(string key) =>
        key.Length <= 12 ? new string('•', key.Length) : $"{key[..7]}…{key[^4..]}";
}
