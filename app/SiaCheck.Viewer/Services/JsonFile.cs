using System.IO;
using System.Text.Json;

namespace SiaCheck.Viewer.Services;

internal static class JsonFile
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

    public static T ReadOrDefault<T>(string path) where T : new()
    {
        try
        {
            if (!File.Exists(path)) return new T();
            using var s = File.OpenRead(path);
            return JsonSerializer.Deserialize<T>(s, Options) ?? new T();
        }
        catch (JsonException)
        {
            // Fichier corrompu : on le met de côté plutôt que de perdre silencieusement la suite.
            File.Copy(path, path + ".corrompu", overwrite: true);
            return new T();
        }
    }

    /// <summary>Écriture atomique : un plantage en cours d'écriture ne détruit pas le fichier précédent.</summary>
    public static void Write<T>(string path, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(value, Options));
        File.Move(tmp, path, overwrite: true);
    }
}
