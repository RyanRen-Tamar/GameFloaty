using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using System.Net;
using System.Threading.Tasks;
using System.Net.Http;
using System.Diagnostics;

namespace GameWikiTooltip
{
    public record AdkRequest(string userId, string conversationId, string query, Dictionary<string, string> context = null);
    public record AdkResponse(string response, string conversationId, Dictionary<string, string> context = null);

    public class GameConfig
    {
        public string BaseUrl { get; set; }
        public bool NeedsSearch { get; set; } = true;
        public string SearchTemplate { get; set; }
        public Dictionary<string, string> KeywordMap { get; set; }
    }
    public class HotkeyConfig
    {
        public string Key { get; set; }
        public string[] Modifiers { get; set; }
    }
    public class AppSettings
    {
        public HotkeyConfig Hotkey { get; set; }
        public PopupConfig Popup { get; set; }
        // Future: Add voice settings here
        // public bool EnableVoiceInput { get; set; } = true;
        // public bool EnableVoiceOutput { get; set; } = true;
        // public string AdkAgentUrl { get; set; } = "http://localhost:5005/invoke_agent";
    }
    public class PopupConfig
    {
        public double Width { get; set; }
        public double Height { get; set; }
        public double Left { get; set; }
        public double Top { get; set; }
    }

    public partial class MainWindow : Window
    {
        // Original placeholder for a direct AI API key, currently unused if ADK flow is primary.
        private string _aiApiKey = "YOUR_API_KEY_HERE";
        private string _lastUrl;
        private NotifyIcon _trayIcon;
        private int _hotkeyId = 9001;
        private AppSettings _settings;
        private Dictionary<string, GameConfig> _gameConfigs;
        private readonly string _userConfigDir;
        private readonly string _userSettingsPath;
        private Window _currentContentPopup;
        private CoreWebView2Environment _sharedEnvironment;

        private static readonly HttpClient httpClient = new HttpClient();
        private string _currentConversationId = null;
        private readonly string _userId = "user_test_001"; // Hardcoded user ID for ADK

        // Voice Settings Placeholders.
        // Future: These should be loaded from AppSettings/settings.json.
        private bool _enableVoiceInput = true;
        private bool _enableVoiceOutput = true;

        // Future: This should be configurable, e.g., from AppSettings/settings.json.
        private readonly string _adkAgentUrl = "http://localhost:5005/invoke_agent";


        [DllImport("user32.dll")]
        private static extern int ShowCursor(int bShow);

        private void ShowCursorUntilVisible()
        {
            while (ShowCursor(1) < 0) { /* keep calling */ }
        }

        public MainWindow()
        {
            InitializeComponent();
            _userConfigDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "GameWikiTooltip");
            Directory.CreateDirectory(_userConfigDir);
            _userSettingsPath = Path.Combine(_userConfigDir, "settings.json");
            InitializeTrayIcon();
            LoadSettings();
            LoadSettingsIntoUI();
            LoadGameConfigs();
            WarmUpWebView2();
            Loaded += MainWindow_Loaded;
        }
        private async void WarmUpWebView2()
        {
            _sharedEnvironment = await CoreWebView2Environment.CreateAsync();
            var hiddenView = new WebView2();
            await hiddenView.EnsureCoreWebView2Async(_sharedEnvironment);
            hiddenView.CoreWebView2.Navigate("about:blank");
        }
        private void InitializeTrayIcon()
        {
            _trayIcon = new NotifyIcon { Visible = false, Text = "Game Wiki Tooltip" };
            try { _trayIcon.Icon = new System.Drawing.Icon("app.ico"); } catch { /* Handle missing icon */ }
            var menu = new ContextMenuStrip();
            menu.Items.Add("设置", null, (s, e) => ShowSettingsWindow());
            menu.Items.Add("退出", null, (s, e) =>
            {
                if (_currentContentPopup != null) { _currentContentPopup.Close(); }
                var handle = new WindowInteropHelper(this).Handle;
                if(handle != IntPtr.Zero) UnregisterHotKey(handle, _hotkeyId);
                if (_trayIcon != null) { _trayIcon.Visible = false; _trayIcon.Dispose(); }
                System.Windows.Application.Current.Shutdown();
            });
             _trayIcon.ContextMenuStrip = menu;
            _trayIcon.DoubleClick += (_, __) => ShowSettingsWindow();
        }
        private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            var result = System.Windows.MessageBox.Show(
                "是要退出程序？点击“否”将最小化到托盘。", "确认", MessageBoxButton.YesNo, MessageBoxImage.Question);

            if (result == MessageBoxResult.No)
            {
                e.Cancel = true;
                Hide();
                if (_trayIcon != null) _trayIcon.Visible = true;
            }
            else
            {
                if (_currentContentPopup != null) { _currentContentPopup.Close(); }
                var handle = new WindowInteropHelper(this).Handle;
                if(handle != IntPtr.Zero) UnregisterHotKey(handle, _hotkeyId);
                if (_trayIcon != null) { _trayIcon.Visible = false; _trayIcon.Dispose(); }
            }
        }
        private void ShowSettingsWindow()
        {
            Show();
            WindowState = WindowState.Normal;
            Activate();
            if (_trayIcon != null) _trayIcon.Visible = false;
        }
        private void BtnSave_Click(object sender, RoutedEventArgs e)
        {
            _settings.Hotkey.Modifiers = new[]
            {
                chkCtrl.IsChecked == true ? "Ctrl" : null,
                chkShift.IsChecked == true ? "Shift" : null,
                chkAlt.IsChecked == true ? "Alt" : null,
                chkWin.IsChecked == true ? "Win" : null
            }.Where(s => s != null).ToArray();
            _settings.Hotkey.Key = cmbKey.SelectedItem.ToString();
            SaveSettings(); // Future: Save voice settings and ADK URL from UI to _settings here.

            var handle = new WindowInteropHelper(this).Handle;
            if(handle != IntPtr.Zero) UnregisterHotKey(handle, _hotkeyId);
            RegisterGlobalHotkey();

            Hide();
            if (_trayIcon != null)
            {
                _trayIcon.Visible = true;
                _trayIcon.BalloonTipTitle = "Game Wiki Tooltip";
                _trayIcon.BalloonTipText = "保存并应用成功！已最小化到系统托盘";
                try { _trayIcon.ShowBalloonTip(3000); } catch { /* Might fail if not Forms NotifyIcon */ }
            }
        }
        private void RegisterGlobalHotkey()
        {
            var handle = new WindowInteropHelper(this).Handle;
            if (handle == IntPtr.Zero) return; // Should not happen if window is loaded
            uint mods = 0;
            foreach (var m in _settings.Hotkey.Modifiers)
                switch (m.ToLowerInvariant())
                {
                    case "ctrl": mods |= 0x0002; break;
                    case "shift": mods |= 0x0004; break;
                    case "alt": mods |= 0x0001; break;
                    case "win": mods |= 0x0008; break;
                }
            uint vk = (uint)KeyInterop.VirtualKeyFromKey(Enum.Parse<Key>(_settings.Hotkey.Key));
            if (!RegisterHotKey(handle, _hotkeyId, mods, vk))
            {
                System.Windows.MessageBox.Show("热键注册失败！可能已被其他程序占用。", "错误", MessageBoxButton.OK, MessageBoxImage.Error);
            }
            HwndSource.FromHwnd(handle)?.AddHook(WndProc);
        }
        [DllImport("user32.dll")]
        private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
        private void LoadSettingsIntoUI()
        {
            // Future: Load voice and ADK URL settings into UI components
            chkCtrl.IsChecked = _settings.Hotkey.Modifiers.Any(m => m.Equals("Ctrl", StringComparison.OrdinalIgnoreCase));
            chkShift.IsChecked = _settings.Hotkey.Modifiers.Any(m => m.Equals("Shift", StringComparison.OrdinalIgnoreCase));
            chkAlt.IsChecked = _settings.Hotkey.Modifiers.Any(m => m.Equals("Alt", StringComparison.OrdinalIgnoreCase));
            chkWin.IsChecked = _settings.Hotkey.Modifiers.Any(m => m.Equals("Win", StringComparison.OrdinalIgnoreCase));

            cmbKey.ItemsSource = Enum.GetValues(typeof(Key)).Cast<Key>()
                                    .Where(k => (k >= Key.F1 && k <= Key.F24) || (k >= Key.A && k <= Key.Z) || (k >= Key.D0 && k <= Key.D9) || (k >= Key.NumPad0 && k <= Key.NumPad9));
            cmbKey.SelectedItem = Enum.TryParse<Key>(_settings.Hotkey.Key, true, out var k) ? k : Key.F12;
        }
        private void LoadSettings()
        {
            // Future: Extend AppSettings to include EnableVoiceInput, EnableVoiceOutput, AdkAgentUrl
            // And deserialize them here. For now, using hardcoded defaults for those.
            if (File.Exists(_userSettingsPath))
            {
                try { _settings = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(_userSettingsPath)); }
                catch (JsonException) { LoadDefaultSettings(true); } // Overwrite corrupted
            }
            else { LoadDefaultSettings(false); } // Create new if not exists
        }
        private void LoadDefaultSettings(bool overwrite)
        {
            string defaultSettingsPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.default.json"); // Example default template
            if (!overwrite && File.Exists(defaultSettingsPath))
            {
                try
                {
                    File.Copy(defaultSettingsPath, _userSettingsPath); // Copy template to user dir
                    _settings = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(_userSettingsPath));
                }
                catch { _settings = GetHardcodedDefaultSettings(); SaveSettings(); }
            }
            else { _settings = GetHardcodedDefaultSettings(); SaveSettings(); } // Use hardcoded if template missing or overwrite needed
        }
        private AppSettings GetHardcodedDefaultSettings() => new AppSettings
        {
            Hotkey = new HotkeyConfig { Key = "F12", Modifiers = new[] { "Ctrl", "Shift" } },
            Popup = new PopupConfig { Width = 800, Height = 600, Left = 100, Top = 100 }
            // Voice settings and ADK URL will use class defaults for now.
        };
        private void SaveSettings()
        {
            try { File.WriteAllText(_userSettingsPath, JsonSerializer.Serialize(_settings, new JsonSerializerOptions { WriteIndented = true, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull })); }
            catch (Exception ex) { System.Windows.MessageBox.Show($"保存设置失败: {ex.Message}", "错误", MessageBoxButton.OK, MessageBoxImage.Error); }
        }
        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            var interopHelper = new WindowInteropHelper(this);
            if (interopHelper.Handle == IntPtr.Zero) interopHelper.EnsureHandle();
            RegisterGlobalHotkey();
        }
        private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            const int WM_HOTKEY = 0x0312;
            if (msg == WM_HOTKEY && wParam.ToInt32() == _hotkeyId)
            {
                _ = Dispatcher.InvokeAsync(ShowWikiWebPopup);
                handled = true;
            }
            return IntPtr.Zero;
        }
        private async Task<string> CaptureAndRecognizeScreenTextAsync()
        {
            await Task.Delay(50);
            return "Simulated OCR result from dummy CaptureAndRecognizeScreenTextAsync method";
        }

        private async Task SimulatePlayTextAsSpeechAsync(string textToPlay)
        {
            // Future: Detect language of textToPlay or use user setting for bilingual TTS.
            Debug.WriteLine($"[TTS SIMULATION] Playing: '{textToPlay}'");
            await Task.Delay(TimeSpan.FromSeconds(1));
        }

        private async Task<string> GetAiResponseAsync(string userQuery, string ocrContextText)
        {
            if (string.IsNullOrWhiteSpace(userQuery)) return "Query cannot be empty.";
            _currentConversationId = Guid.NewGuid().ToString();
            var contextData = new Dictionary<string, string>();
            if (!string.IsNullOrEmpty(ocrContextText)) contextData["screen_text"] = ocrContextText;

            var requestPayload = new AdkRequest(_userId, _currentConversationId, userQuery, contextData.Count > 0 ? contextData : null);
            string jsonRequest;
            try { jsonRequest = JsonSerializer.Serialize(requestPayload); }
            catch (JsonException ex) { return $"Error: Failed to serialize ADK request. {ex.Message}"; }

            // Simulate HTTP call to ADK agent
            // Future: ADK_AGENT_URL should be configurable, e.g., from AppSettings/settings.json.
            // var targetUrl = _settings.AdkAgentUrl ?? _adkAgentUrl; // Prioritize settings
            try
            {
                await Task.Delay(150); // Simulate network latency for httpClient.PostAsync(_adkAgentUrl, ...)
                string simulatedJsonResponse;

                if (userQuery.ToLowerInvariant() == "error_adk")
                {
                    // This specific string will be checked in ShowWikiWebPopup for special formatting.
                    return $"ADK Agent Error: Simulated error processing the request for '{userQuery}'. ConvID: {_currentConversationId}";
                }
                else if (userQuery.ToLowerInvariant() == "error") // General non-ADK error
                {
                     return "Error: Simulated general error occurred while fetching the AI response.";
                }
                else
                {
                    string responseText = $"ADK Agent Mock Says: Your query was '{userQuery}'. ConvID: {_currentConversationId}.";
                    if (requestPayload.context != null && requestPayload.context.TryGetValue("screen_text", out var screenText))
                    {
                        responseText += $" I see on your screen: '{screenText}'.";
                    }
                    var adkResponse = new AdkResponse(responseText, _currentConversationId, requestPayload.context);
                    simulatedJsonResponse = JsonSerializer.Serialize(adkResponse);
                }

                AdkResponse deserializedResponse = JsonSerializer.Deserialize<AdkResponse>(simulatedJsonResponse);
                if (deserializedResponse != null && !string.IsNullOrEmpty(deserializedResponse.response))
                {
                    _currentConversationId = deserializedResponse.conversationId;
                    return deserializedResponse.response;
                }
                // This path might be hit if simulatedJsonResponse was an error JSON not matching AdkResponse structure.
                return "ADK Error: Failed to deserialize valid ADK response or response was empty.";
            }
            catch (JsonException ex) { return $"JSON Error: Could not process ADK response. {ex.Message}"; }
            catch (Exception ex) { return $"Error: An unexpected error occurred communicating with ADK. {ex.Message}"; }
        }

        private async void ShowWikiWebPopup()
        {
            // --- Game Configuration Check ---
            string title = GetActiveWindowTitle();
            GameConfig cfg = null;
            foreach (var kv in _gameConfigs)
            {
                if (title.Contains(kv.Key, StringComparison.OrdinalIgnoreCase)) { cfg = kv.Value; break; }
            }
            if (cfg == null)
            {
                System.Windows.MessageBox.Show($"暂不支持游戏：{title}\n请在 games.json 添加条目。", "提示", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            // --- Input Gathering (Prompt / Future STT) ---
            // If _enableVoiceInput is true, Prompt.ShowDialogAsync could be replaced or augmented
            // by a voice recognition step that populates 'input'.
            // Future: if (_enableVoiceInput) { input = await RecognizeSpeechAsync(); } else { input = await Prompt.ShowDialogAsync(...); }
            string input = await Prompt.ShowDialogAsync("输入AI查询或关键词…");
            if (string.IsNullOrWhiteSpace(input)) return;

            if (input == "<<LAST>>")
            {
                if (_currentContentPopup != null) _currentContentPopup.Activate();
                else System.Windows.MessageBox.Show("没有活动的AI查询弹窗。上次AI查询重放功能尚未实现。", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            // --- Context Gathering (Future Screen Capture + OCR) ---
            // string actualOcrText = await CaptureAndRecognizeScreenTextAsync(); // Future real call
            string simulatedOcrText = "Simulated OCR: Player is facing 'Dragonlord Placidusax'. Health: 50%. Location: Crumbling Farum Azula.";

            // --- Calling the AI Agent ---
            string aiResponse = await GetAiResponseAsync(input, simulatedOcrText);

            // --- Prepare HTML for WebView ---
            string htmlContent;
            bool isErrorResponse = string.IsNullOrEmpty(aiResponse) ||
                                   aiResponse.StartsWith("Error:") ||
                                   aiResponse.StartsWith("ADK Error:") ||
                                   aiResponse.StartsWith("JSON Error:");

            if (isErrorResponse)
            {
                string errorMessage = string.IsNullOrEmpty(aiResponse) ? "AI did not return a response." : aiResponse;
                htmlContent = $"<html><head><meta charset=\"UTF-8\"></head><body><h3>Error:</h3><pre style='color:red;'>{WebUtility.HtmlEncode(errorMessage)}</pre></body></html>";
            }
            else
            {
                htmlContent = $"<html><head><meta charset=\"UTF-8\"></head><body><h3>Query:</h3><p>{WebUtility.HtmlEncode(input)}</p>";
                if (!string.IsNullOrEmpty(simulatedOcrText))
                {
                     htmlContent += $"<h3>OCR Context:</h3><p><small>{WebUtility.HtmlEncode(simulatedOcrText)}</small></p>";
                }
                htmlContent += $"<h3>Response from ADK Agent:</h3><pre>{WebUtility.HtmlEncode(aiResponse)}</pre></body></html>";
            }

            // --- Simulated TTS Output ---
            // Play TTS only for non-error responses and if enabled
            if (!isErrorResponse && _enableVoiceOutput && !string.IsNullOrEmpty(aiResponse))
            {
                _ = SimulatePlayTextAsSpeechAsync(aiResponse);
            }

            // --- Displaying response in WebView2 ---
            if (_currentContentPopup != null) { _currentContentPopup.Close(); _currentContentPopup = null; }

            var popup = new Window
            {
                Title = isErrorResponse ? "AI Error" : "ADK AI Response",
                Width = _settings.Popup.Width, Height = _settings.Popup.Height,
                Left = _settings.Popup.Left, Top = _settings.Popup.Top,
                Topmost = true, WindowStartupLocation = WindowStartupLocation.Manual, ShowInTaskbar = false
            };
            var container = new Grid();
            var webView = new WebView2 { Visibility = Visibility.Hidden };
            var overlayTextBlock = new TextBlock { Text = "正在加载响应…", FontSize = 16, FontWeight = FontWeights.Bold, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
            var overlay = new Border { Background = new SolidColorBrush(System.Windows.Media.Color.FromArgb(180, 255, 255, 255)), Child = overlayTextBlock };

            container.Children.Add(webView);
            container.Children.Add(overlay);
            popup.Content = container;
            popup.Loaded += (_, __) => popup.Activate();
            popup.Show();

            await webView.EnsureCoreWebView2Async(_sharedEnvironment);
            webView.CoreWebView2.NewWindowRequested += (s, e) => { e.Handled = true; webView.CoreWebView2.Navigate(e.Uri); };
            webView.CoreWebView2.NavigateToString(htmlContent);
            webView.NavigationStarting += (s, e) => { overlay.Visibility = Visibility.Visible; webView.Visibility = Visibility.Hidden; };
            webView.NavigationCompleted += (s, e) => { overlay.Visibility = Visibility.Collapsed; webView.Visibility = Visibility.Visible; };
            popup.Closed += (s, e) =>
            {
                _settings.Popup.Left = popup.Left; _settings.Popup.Top = popup.Top;
                _settings.Popup.Width = popup.Width; _settings.Popup.Height = popup.Height;
                SaveSettings();
                _currentContentPopup = null;
                if (webView != null && webView.CoreWebView2 != null) { webView.CoreWebView2.Stop(); webView.Dispose(); }
            };
            _currentContentPopup = popup;
        }

        private void LoadGameConfigs()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "games.json");
            if (!File.Exists(path))
            {
                System.Windows.MessageBox.Show("缺少文件games.json,检查下载是否完全");
                _gameConfigs = new Dictionary<string, GameConfig>(StringComparer.OrdinalIgnoreCase); return;
            }
            try
            {
                var doc = JsonDocument.Parse(File.ReadAllText(path));
                _gameConfigs = new Dictionary<string, GameConfig>(StringComparer.OrdinalIgnoreCase);
                foreach (var prop in doc.RootElement.EnumerateObject())
                {
                    if (prop.Value.ValueKind == JsonValueKind.Object)
                    {
                        var gameCfg = prop.Value.Deserialize<GameConfig>();
                        if (gameCfg.NeedsSearch && string.IsNullOrWhiteSpace(gameCfg.SearchTemplate)) gameCfg.SearchTemplate = "{baseUrl}/{keyword}";
                        _gameConfigs[prop.Name] = gameCfg;
                    }
                    else if (prop.Value.ValueKind == JsonValueKind.String)
                    {
                        _gameConfigs[prop.Name] = new GameConfig { BaseUrl = prop.Value.GetString(), NeedsSearch = true, SearchTemplate = "{baseUrl}/{keyword}" };
                    }
                }
            }
            catch (JsonException ex)
            {
                 System.Windows.MessageBox.Show($"解析 games.json 失败: {ex.Message}\n将使用空配置。", "错误", MessageBoxButton.OK, MessageBoxImage.Error);
                _gameConfigs = new Dictionary<string, GameConfig>(StringComparer.OrdinalIgnoreCase);
            }
        }
        private string GetActiveWindowTitle()
        {
            const int nChars = 256;
            StringBuilder buff = new StringBuilder(nChars);
            IntPtr handle = GetForegroundWindow();
            return GetWindowText(handle, buff, nChars) > 0 ? buff.ToString() : null;
        }

        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();
    }

    public static class Prompt
    {
        private static Window _currentPrompt;
        public static Task<string> ShowDialogAsync(string placeholder = "输入关键词…")
        {
            if (_currentPrompt != null && _currentPrompt.IsVisible)
            {
                _currentPrompt.Activate();
                return Task.FromResult<string>(null);
            }
            var tcs = new TaskCompletionSource<string>();
            var prompt = new Window
            {
                Width = 400, Height = 100, WindowStyle = WindowStyle.None, AllowsTransparency = true,
                Background = System.Windows.Media.Brushes.Transparent, Opacity = 0.85, Topmost = true,
                ShowInTaskbar = false, WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            _currentPrompt = prompt;
            prompt.Closed += (_, __) => { _currentPrompt = null; if (!tcs.Task.IsCompleted) tcs.TrySetResult(null); };
            prompt.Deactivated += (s, e) => { if (prompt.IsVisible) prompt.Close(); };
            prompt.PreviewKeyDown += (s, e) => { if (e.Key == Key.Escape) prompt.Close(); };
            var border = new Border { CornerRadius = new CornerRadius(10), Background = new SolidColorBrush(System.Windows.Media.Color.FromArgb(240, 255, 255, 255)), Padding = new Thickness(10) };
            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var icon = new TextBlock { FontFamily = new System.Windows.Media.FontFamily("Segoe MDL2 Assets"), Text = "\uE721", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 10, 0), FontSize = 16 };
            Grid.SetColumn(icon, 0);
            var inputTextBox = new System.Windows.Controls.TextBox { Background = Brushes.Transparent, BorderThickness = new Thickness(0), VerticalContentAlignment = VerticalAlignment.Center, FontSize = 16, Foreground = Brushes.Black, Text = "" };
            var placeholderAdorner = new TextBlock { Text = placeholder, Foreground = Brushes.Gray, IsHitTestVisible = false, Visibility = Visibility.Collapsed, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(2,0,0,0) };
            if(string.IsNullOrEmpty(inputTextBox.Text)) placeholderAdorner.Visibility = Visibility.Visible;
            inputTextBox.TextChanged += (s,e) => { placeholderAdorner.Visibility = string.IsNullOrEmpty(inputTextBox.Text) ? Visibility.Visible : Visibility.Collapsed; };
            var inputGrid = new Grid();
            inputGrid.Children.Add(inputTextBox);
            inputGrid.Children.Add(placeholderAdorner);
            Grid.SetColumn(inputGrid, 1);
            grid.Children.Add(icon);
            grid.Children.Add(inputGrid);
            border.Child = grid;
            inputTextBox.KeyDown += (s, e) => { if (e.Key == Key.Enter) { prompt.Close(); tcs.TrySetResult(inputTextBox.Text); }};
            var lastBtn = new System.Windows.Controls.Button { Content = "打开上次内容", Opacity = 0.9, Background = Brushes.LightGray, BorderBrush = Brushes.DarkGray, BorderThickness = new Thickness(1), Height = 30, Width = 120, FontSize = 11, Padding = new Thickness(8), HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 8, 0, 0) };
            lastBtn.Click += (s, e) => { prompt.Close(); tcs.TrySetResult("<<LAST>>"); };
            var panel = new StackPanel();
            panel.Children.Add(border);
            panel.Children.Add(lastBtn);
            prompt.Content = panel;
            prompt.Loaded += (_, __) => { prompt.Activate(); inputTextBox.Focus(); };
            prompt.Show();
            return tcs.Task;
        }
    }
}
