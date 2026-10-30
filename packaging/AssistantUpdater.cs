using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

// Small Windows helper. No PowerShell, shell commands or changes to execution policy.
internal static class AssistantUpdater
{
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

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

    private static void Status(string path, bool success, string message)
    {
        File.WriteAllText(path, Json.Serialize(new { success = success, message = message }),
                          new UTF8Encoding(false));
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
        bool applicationClosed = false;
        try
        {
            if (args.Length != 1) return 2;
            parameters = Absolute(args[0]);
            string cache = Path.GetDirectoryName(parameters);
            var data = Json.Deserialize<Dictionary<string, object>>(
                File.ReadAllText(parameters, Encoding.UTF8));
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
                if (previous != null && !previous.WaitForExit(120000))
                    throw new TimeoutException("O aplicativo não encerrou a tempo. Nenhum processo foi forçado a fechar.");
            }
            applicationClosed = true;
            WaitForAllInstances(executable);
            WaitForImageRelease(executable);

            using (var source = File.OpenRead(installer))
            using (var sha = SHA256.Create())
            {
                string actual = BitConverter.ToString(sha.ComputeHash(source)).Replace("-", "").ToLowerInvariant();
                if (actual != hash)
                    throw new InvalidDataException("O instalador mudou antes da instalação. Atualização cancelada.");
            }
            string options = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCLOSEAPPLICATIONS " +
                             "/NORESTARTAPPLICATIONS /DIR=\"" + directory + "\" /LOG=\"" + log + "\"";
            using (Process installation = Process.Start(new ProcessStartInfo(installer, options) {
                UseShellExecute = false, CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            }))
            {
                installation.WaitForExit();
                if (installation.ExitCode != 0)
                    throw new InvalidOperationException(
                        (installation.ExitCode == 5 ?
                            "O Windows impediu substituir os arquivos do aplicativo; " +
                            "eles podem estar em uso por outra instância. " : "") +
                        "O instalador retornou o código " + installation.ExitCode + ". Consulte install.log.");
            }
            Status(status, true, "Atualização instalada.");
            File.Delete(marker);
            Restart(executable);
            return 0;
        }
        catch (Exception error)
        {
            if (marker != null) { try { File.Delete(marker); } catch { } }
            if (status != null)
            {
                try { Status(status, false, error.Message); } catch { }
            }
            if (applicationClosed && executable != null && File.Exists(executable))
            {
                try { Restart(executable); } catch { }
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
