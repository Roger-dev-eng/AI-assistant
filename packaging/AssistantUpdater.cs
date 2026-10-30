using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

// Small Windows helper. No PowerShell, shell commands or changes to execution policy.
internal static class AssistantUpdater
{
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 4194304 };
    private static string tracePath;

    private static void Trace(string stage, int? code = null, string errorType = null)
    {
        if (tracePath == null) return;
        try
        {
            using (var stream = new FileStream(tracePath, FileMode.Append, FileAccess.Write, FileShare.Read))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
            {
                writer.WriteLine(Json.Serialize(new {
                    time = DateTime.UtcNow.ToString("o"), pid = Process.GetCurrentProcess().Id,
                    stage = stage, code = code, error_type = errorType
                }));
                writer.Flush();
                stream.Flush(true);
            }
        }
        catch { } // Diagnostics must not change update behavior.
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr owner, string text, string title, uint type);

    private static string Text(Dictionary<string, object> data, string key)
    {
        return Convert.ToString(data[key]);
    }

    private static string Absolute(string value)
    {
        if (String.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value) ||
            value.IndexOfAny(new char[] { '"', '\r', '\n' }) >= 0)
            throw new InvalidDataException("Caminho de atualização inválido.");
        return Path.GetFullPath(value);
    }

    private static bool Same(string left, string right)
    {
        return String.Equals(left, right, StringComparison.OrdinalIgnoreCase);
    }

    private static void Status(string path, bool success, string message, string installedVersion = null)
    {
        File.WriteAllText(path, Json.Serialize(new {
            success = success, message = message, installed_version = installedVersion
        }),
                          new UTF8Encoding(false));
    }

    private static Dictionary<string, object> ReadManifest(string directory)
    {
        string path = Path.Combine(directory, "application-manifest.json");
        if (new FileInfo(path).Length > 4194304)
            throw new InvalidDataException("Manifesto da instalação grande demais.");
        return Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
    }

    private static string FileHash(string path)
    {
        using (var source = File.OpenRead(path))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(source)).Replace("-", "").ToLowerInvariant();
    }

    private static string OwnedPath(string directory, string relative)
    {
        if (Path.IsPathRooted(relative) || relative.IndexOf(':') >= 0 ||
            relative.IndexOf('\\') >= 0 || relative.IndexOf('\0') >= 0)
            throw new InvalidDataException("Caminho inválido no manifesto.");
        foreach (string part in relative.Split('/'))
            if (part == "" || part == "." || part == ".." || part.EndsWith(".") || part.EndsWith(" "))
                throw new InvalidDataException("Caminho inválido no manifesto.");
        string root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
        string target = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!target.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Arquivo fora da instalação.");
        string current = root;
        if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("A instalação usa um redirecionamento de pasta.");
        foreach (string part in relative.Split('/'))
        {
            current = Path.Combine(current, part);
            if ((Directory.Exists(current) || File.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("O manifesto aponta para um redirecionamento.");
        }
        return target;
    }

    private static Dictionary<string, object> VerifyInstallation(string directory, string expectedVersion)
    {
        var manifest = ReadManifest(directory);
        if (Text(manifest, "version") != expectedVersion)
            throw new InvalidDataException("O instalador terminou, mas a versão instalada não é " + expectedVersion + ".");
        var files = (Dictionary<string, object>)manifest["files"];
        string expectedHash = Text(files, "AssistantDesktop.exe");
        if (!Regex.IsMatch(expectedHash, @"\A[a-f0-9]{64}\z") ||
            FileHash(OwnedPath(directory, "AssistantDesktop.exe")) != expectedHash)
            throw new InvalidDataException("O executável instalado não corresponde à versão esperada.");
        return files;
    }

    private static void RemoveObsoleteFiles(string directory, Dictionary<string, object> previous,
                                             Dictionary<string, object> installed)
    {
        if (previous == null || !previous.ContainsKey("files")) return;
        var files = previous["files"] as Dictionary<string, object>;
        if (files == null) return;
        var activePaths = new HashSet<string>(installed.Keys, StringComparer.OrdinalIgnoreCase);
        foreach (var entry in files)
        {
            if (activePaths.Contains(entry.Key)) continue;
            try
            {
                string name = Path.GetFileName(entry.Key).ToLowerInvariant();
                string extension = Path.GetExtension(name);
                // Databases, credentials and preferences are never cleanup targets,
                // even if an old or tampered manifest claims ownership of them.
                if (name.StartsWith(".env", StringComparison.Ordinal) || name == "settings.json" || name == "credentials" ||
                    name == "config" || name == "application-manifest.json" ||
                    extension.StartsWith(".db") || extension.StartsWith(".sqlite")) continue;
                // Only program binaries and versioned bundled browser files can become obsolete.
                // User-selected voice models and arbitrary documents remain untouched.
                if (!(extension == ".dll" || extension == ".pyd" ||
                      entry.Key.StartsWith("_internal/browsers/", StringComparison.Ordinal))) continue;
                string path = OwnedPath(directory, entry.Key);
                string hash = Convert.ToString(entry.Value);
                if (File.Exists(path) && Regex.IsMatch(hash, @"\A[a-f0-9]{64}\z") && FileHash(path) == hash)
                {
                    File.Delete(path);
                    Trace("cleanup.obsolete_file.removed");
                }
            }
            catch (Exception error) { Trace("cleanup.file.preserved", null, error.GetType().Name); }
        }
    }

    private static bool OtherInstance(string executable)
    {
        foreach (Process candidate in Process.GetProcessesByName("AssistantDesktop"))
        using (candidate)
        {
            try
            {
                if (Same(candidate.MainModule.FileName, executable)) return true;
            }
            catch (InvalidOperationException) { } // Process exited during enumeration.
            catch (System.ComponentModel.Win32Exception)
            {
                if (candidate.SessionId == Process.GetCurrentProcess().SessionId)
                    throw new InvalidOperationException("Não foi possível verificar outra cópia do assistente.");
            }
        }
        return false;
    }

    private static void WaitForAllInstances(string executable)
    {
        Stopwatch timer = Stopwatch.StartNew();
        while (OtherInstance(executable))
        {
            if (timer.ElapsedMilliseconds >= 10000)
                throw new InvalidOperationException("Outra cópia do assistente continua aberta. " +
                    "Feche todas as cópias pelo menu Aplicativo → Sair antes de atualizar.");
            Thread.Sleep(100);
        }
    }

    private static void Restart(string executable)
    {
        if (OtherInstance(executable)) return;
        Process.Start(new ProcessStartInfo(executable, "--gui") {
            UseShellExecute = false, CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        });
    }

    private static void WaitForImageRelease(string executable)
    {
        if (!File.Exists(executable)) return;
        Stopwatch timer = Stopwatch.StartNew();
        while (true)
        {
            try
            {
                // No bytes are written. Exclusive access checks that Windows has
                // released the image before the installer attempts replacement.
                using (File.Open(executable, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                return;
            }
            catch (Exception error)
            {
                if (!(error is IOException) && !(error is UnauthorizedAccessException)) throw;
                if (timer.ElapsedMilliseconds >= 10000)
                    throw new InvalidOperationException("O arquivo do aplicativo ainda está em uso " +
                        "ou sem permissão de substituição. A instalação não foi iniciada.", error);
                Thread.Sleep(100);
            }
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string parameters = null, status = null, executable = null, marker = null;
        bool readySent = false, notifyFailure = false;
        try
        {
            if (args.Length != 1) return 2;
            parameters = Absolute(args[0]);
            string cache = Path.GetDirectoryName(parameters);
            var data = Json.Deserialize<Dictionary<string, object>>(
                File.ReadAllText(parameters, Encoding.UTF8));
            notifyFailure = data.ContainsKey("notify_failure") && Convert.ToBoolean(data["notify_failure"]);
            string installer = Absolute(Text(data, "installer"));
            executable = Absolute(Text(data, "executable"));
            string directory = Absolute(Text(data, "directory"));
            string ready = Absolute(Text(data, "ready"));
            string log = Absolute(Text(data, "log"));
            string statusCandidate = Absolute(Text(data, "status"));
            if (!Same(Path.GetDirectoryName(statusCandidate), cache))
                throw new InvalidDataException("Destino do relatório inválido.");
            status = statusCandidate;
            string hash = Text(data, "sha256");
            if (!Same(Path.GetDirectoryName(installer), cache) ||
                !Same(Path.GetDirectoryName(ready), cache) ||
                !Same(Path.GetDirectoryName(log), cache) ||
                !Same(Path.GetDirectoryName(executable), directory) ||
                !Same(Path.GetFileName(executable), "AssistantDesktop.exe") ||
                !Regex.IsMatch(Path.GetFileName(installer), @"\AAssistantDesktop-\d+\.\d+\.\d+-Setup\.exe\z") ||
                !Regex.IsMatch(hash, @"\A[a-f0-9]{64}\z"))
                throw new InvalidDataException("Parâmetros de atualização inválidos.");

            tracePath = Path.Combine(cache, "updater-" + Process.GetCurrentProcess().Id + ".jsonl");
            Trace("manifest.validated");
            string expectedVersion = Path.GetFileName(installer).Substring("AssistantDesktop-".Length);
            expectedVersion = expectedVersion.Substring(0, expectedVersion.Length - "-Setup.exe".Length);
            if (data.ContainsKey("expected_version") && Text(data, "expected_version") != expectedVersion)
                throw new InvalidDataException("Versão solicitada diferente do instalador.");

            Process previous = null;
            try { previous = Process.GetProcessById(Convert.ToInt32(data["process"])); }
            catch (ArgumentException) { }
            using (previous)
            {
                if (previous != null && !Same(previous.MainModule.FileName, executable))
                    throw new InvalidDataException("O processo informado não é o assistente.");
                marker = Path.Combine(cache, "active-update.json");
                using (Process updater = Process.GetCurrentProcess())
                    File.WriteAllText(marker, Json.Serialize(new {
                        process = updater.Id, executable = updater.MainModule.FileName
                    }), new UTF8Encoding(false));
                File.WriteAllText(ready, "ready");
                readySent = true;
                Trace("application.exit.wait.begin");
                if (previous != null && !previous.WaitForExit(120000))
                    throw new TimeoutException("O aplicativo não encerrou a tempo. Nenhum processo foi forçado a fechar.");
            }
            Trace("application.exit.wait.end");
            Trace("instances.wait.begin");
            WaitForAllInstances(executable);
            Trace("instances.wait.end");
            Trace("image.release.wait.begin");
            WaitForImageRelease(executable);
            Trace("image.release.wait.end");

            Trace("installer.hash.begin");
            using (var source = File.OpenRead(installer))
            using (var sha = SHA256.Create())
            {
                string actual = BitConverter.ToString(sha.ComputeHash(source)).Replace("-", "").ToLowerInvariant();
                if (actual != hash)
                    throw new InvalidDataException("O instalador mudou antes da instalação. Atualização cancelada.");
            }
            Trace("installer.hash.end");
            Dictionary<string, object> previousManifest = null;
            try { previousManifest = ReadManifest(directory); }
            catch { Trace("manifest.previous.unavailable"); }
            Trace("installer.start");
            string options = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCLOSEAPPLICATIONS " +
                             "/NORESTARTAPPLICATIONS /DIR=\"" + directory + "\" /LOG=\"" + log + "\"";
            using (Process installation = Process.Start(new ProcessStartInfo(installer, options) {
                UseShellExecute = false, CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            }))
            {
                installation.WaitForExit();
                Trace("installer.exit", installation.ExitCode);
                if (installation.ExitCode != 0)
                    throw new InvalidOperationException(
                        (installation.ExitCode == 5 ?
                            "O Windows impediu substituir os arquivos do aplicativo; " +
                            "eles podem estar em uso por outra instância. " : "") +
                        "O instalador retornou o código " + installation.ExitCode + ". Consulte install.log.");
            }
            Trace("installation.verify.begin");
            var installedFiles = VerifyInstallation(directory, expectedVersion);
            Trace("installation.verify.end");
            RemoveObsoleteFiles(directory, previousManifest, installedFiles);
            Status(status, true, "Atualização instalada e verificada: " + expectedVersion + ".", expectedVersion);
            File.Delete(marker);
            Trace("application.restart.begin");
            Restart(executable);
            Trace("application.restart.end");
            return 0;
        }
        catch (Exception error)
        {
            Trace("update.failed", null, error.GetType().Name);
            if (marker != null) { try { File.Delete(marker); } catch { } }
            if (status != null)
            {
                try { Status(status, false, error.Message); } catch { }
            }
            if (readySent && notifyFailure)
            {
                MessageBox(IntPtr.Zero, error.Message +
                    "\n\nA atualização não foi concluída. O assistente não foi reaberto automaticamente. " +
                    "Consulte o arquivo install.log na pasta de atualizações.", "Falha na atualização", 0x10);
            }
            return 1;
        }
        finally
        {
            if (marker != null) { try { File.Delete(marker); } catch { } }
            if (parameters != null)
            {
                try { File.Delete(parameters); } catch { }
            }
        }
    }
}
