using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;

namespace GameWikiTooltip
{
    // 用于反序列化 games.json
    public class GameConfig
    {
        public string BaseUrl { get; set; }
        public bool NeedsSearch { get; set; } = true;
        public string SearchTemplate { get; set; }
        public Dictionary<string, string> KeywordMap { get; set; }
    }
    // 对应 settings.json 结构
    public class HotkeyConfig
    {
        public string Key { get; set; }
        public string[] Modifiers { get; set; }
    }
    public class AppSettings
    {
        public HotkeyConfig Hotkey { get; set; }
        public PopupConfig Popup { get; set; }
    }
    // games.json
    public class PopupConfig
    {
        public double Width { get; set; }
        public double Height { get; set; }
        public double Left { get; set; }
        public double Top { get; set; }
    }

    //
    public partial class MainWindow : Window
    {
        private string _lastUrl;  // 记录上一次打开的 URL
        private NotifyIcon _trayIcon; //托盘图标
        private int _hotkeyId = 9001;
        private AppSettings _settings;
        private Dictionary<string, GameConfig> _gameConfigs;
        private readonly string _userConfigDir;
        private readonly string _userSettingsPath;
        // 新增：跟踪当前打开的内容浮窗
        private Window _currentContentPopup;
        // 共享的 WebView2 环境
        private CoreWebView2Environment _sharedEnvironment;
        [DllImport("user32.dll")]
        private static extern int ShowCursor(int bShow);

        /// <summary>
        /// 不断调用 ShowCursor(1) 直到内部计数 >= 0，使光标显示出来
        /// </summary>
        private void ShowCursorUntilVisible()
        {
            while (ShowCursor(1) < 0)
            {
                // keep calling
            }
        }

        public MainWindow()
        {
            InitializeComponent();
            // 1) 构造 AppData 下的配置目录和文件路径
            _userConfigDir = Path.Combine(
                                     Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                                     "GameWikiTooltip");
            Directory.CreateDirectory(_userConfigDir);
            _userSettingsPath = Path.Combine(_userConfigDir, "settings.json");
            InitializeTrayIcon();
            LoadSettings();
            LoadSettingsIntoUI();
            LoadGameConfigs();
            WarmUpWebView2();
            Loaded += MainWindow_Loaded;
        }
        //浮窗预启动
        private async void WarmUpWebView2()
        {
            // 创建共享环境（可自定义 UserDataFolder 等）
            _sharedEnvironment = await CoreWebView2Environment.CreateAsync();
            // 隐藏的 WebView2 控件
            var hiddenView = new WebView2();
            await hiddenView.EnsureCoreWebView2Async(_sharedEnvironment);
            // 加载一个空白或本地资源，保持环境“热”着
            hiddenView.CoreWebView2.Navigate("about:blank");
            // 不要添加到可视树，直接丢掉引用即可
        }
        //托盘初始化
        private void InitializeTrayIcon()
        {
            _trayIcon = new NotifyIcon
            {
                Icon = new System.Drawing.Icon("app.ico"), // 你的图标文件
                Visible = false,
                Text = "Game Wiki Tooltip"
            };
            // 创建右键菜单
            var menu = new ContextMenuStrip();
            menu.Items.Add("设置", null, (s, e) => ShowSettingsWindow());
            menu.Items.Add("退出", null, (s, e) =>
            {
                // 清理全局热键
                var handle = new WindowInteropHelper(this).Handle;
                UnregisterHotKey(handle, _hotkeyId);

                _trayIcon.Visible = false;
                System.Windows.Application.Current.Shutdown();
            });
            _trayIcon.ContextMenuStrip = menu;

            _trayIcon.DoubleClick += (_, __) => ShowSettingsWindow();
        }

        private void ShowSettingsWindow()
        {
            // 保证主窗口可见并激活
            Show();
            WindowState = WindowState.Normal;
            Activate();
            _trayIcon.Visible = false;
        }

        //最小化到脱盘// XAML: <Window … Closing="Window_Closing">
        private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            var result = System.Windows.MessageBox.Show(
                "是要退出程序？点击“否”将最小化到托盘。",
                "确认",
                MessageBoxButton.YesNo,
                MessageBoxImage.Question);

            if (result == MessageBoxResult.No)
            {
                e.Cancel = true;    // 取消真正的关闭
                Hide();             // 隐藏窗口
                _trayIcon.Visible = true;
            }
            // 如果是 Yes，就让窗口正常关闭，释放热键等资源
        }
        //“保存并应用热键”按钮
        private void BtnSave_Click(object sender, RoutedEventArgs e)
        {
            // 读取 UI 勾选框和下拉框的值到 _settings.Hotkey
            _settings.Hotkey.Modifiers = new[]
            {
                chkCtrl.IsChecked == true ? "Ctrl" : null,
                chkShift.IsChecked == true ? "Shift" : null,
                chkAlt.IsChecked == true ? "Alt" : null,
                chkWin.IsChecked == true ? "Win" : null
            }.Where(s => s != null).ToArray();
            _settings.Hotkey.Key = cmbKey.SelectedItem.ToString();
            SaveSettings();              // 写回 settings.json

            // 取消旧热键、注册新热键
            var handle = new WindowInteropHelper(this).Handle;
            UnregisterHotKey(handle, _hotkeyId);
            RegisterGlobalHotkey();
            Hide();             // 隐藏窗口
            _trayIcon.Visible = true;

            // 设置气泡提示内容
            _trayIcon.BalloonTipTitle = "Game Wiki Tooltip";
            _trayIcon.BalloonTipText = "保存并应用成功！已最小化到系统托盘";
            _trayIcon.BalloonTipIcon = ToolTipIcon.Info;

            // 显示气泡提示，持续 3 秒（3000 毫秒）
            Dispatcher.InvokeAsync(() => _trayIcon.ShowBalloonTip(3000),
                       DispatcherPriority.ApplicationIdle);
        }

        private void RegisterGlobalHotkey()
        {
            var handle = new WindowInteropHelper(this).Handle;
            uint mods = 0;
            foreach (var m in _settings.Hotkey.Modifiers)
                switch (m)
                {
                    case "Ctrl": mods |= 0x0002; break;
                    case "Shift": mods |= 0x0004; break;
                    case "Alt": mods |= 0x0001; break;
                    case "Win": mods |= 0x0008; break;
                }
            uint vk = (uint)KeyInterop.VirtualKeyFromKey(Enum.Parse<Key>(_settings.Hotkey.Key));
            RegisterHotKey(handle, _hotkeyId, mods, vk);
            HwndSource.FromHwnd(handle).AddHook(WndProc);
        }

        [DllImport("user32.dll")]
        private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

        private void LoadSettingsIntoUI()
        {
            chkCtrl.IsChecked = _settings.Hotkey.Modifiers.Contains("Ctrl");
            chkShift.IsChecked = _settings.Hotkey.Modifiers.Contains("Shift");
            chkAlt.IsChecked = _settings.Hotkey.Modifiers.Contains("Alt");
            chkWin.IsChecked = _settings.Hotkey.Modifiers.Contains("Win");

            cmbKey.ItemsSource = Enum.GetValues(typeof(Key))
                                    .Cast<Key>()
                                    .Where(k => (k >= Key.F1 && k <= Key.F24) || (k >= Key.A && k <= Key.Z));
            cmbKey.SelectedItem = Enum.TryParse<Key>(_settings.Hotkey.Key, true, out var k) ? k : Key.F12;
        }


        //原有
        private void LoadSettings()
        {
            // 如果 AppData 目录里已有用户配置，就直接读它
            if (File.Exists(_userSettingsPath))
            {
                var json = File.ReadAllText(_userSettingsPath);
                _settings = JsonSerializer.Deserialize<AppSettings>(json);
            }
            else
            {
                // 否则，从程序目录的默认 settings.json 拷贝一份到 AppData
                string defaultPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.json");
                if (File.Exists(defaultPath))
                {
                    File.Copy(defaultPath, _userSettingsPath);
                    var json = File.ReadAllText(_userSettingsPath);
                    _settings = JsonSerializer.Deserialize<AppSettings>(json);
                }
                else
                {
                    // 既没有用户文件，也没有默认文件，则用硬编码的默认
                    _settings = new AppSettings
                    {
                        Hotkey = new HotkeyConfig { Key = "F", Modifiers = new[] { "Ctrl" } },
                        Popup = new PopupConfig { Width = 800, Height = 600, Left = 100, Top = 100 }
                    };
                    // 并且写一份到 AppData
                    SaveSettings();
                }
            }
        }

        private void SaveSettings()
        {
            var options = new JsonSerializerOptions { WriteIndented = true };
            File.WriteAllText(_userSettingsPath, JsonSerializer.Serialize(_settings, options));
        }

        private void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
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
        //wiki浮窗
        private async void ShowWikiWebPopup()
        {
            // 1. 读前台窗口标题
            string title = GetActiveWindowTitle();

            // 如果是 CS2 或 Valorant 且浮窗已存在，则呼出光标，不打开新窗口
            if (_currentContentPopup != null
                && (title.Contains("Counter-Strike 2", StringComparison.OrdinalIgnoreCase)
                    || title.Contains("VALORANT", StringComparison.OrdinalIgnoreCase) 
                    || title.Contains("三角洲行动", StringComparison.OrdinalIgnoreCase)))
            {
                ShowCursorUntilVisible();

                // 如果浮窗被最小化，就恢复到正常窗口
                if (_currentContentPopup.WindowState == WindowState.Minimized)
                    _currentContentPopup.WindowState = WindowState.Normal;

                _currentContentPopup.Activate();  // 聚焦已有浮窗
                return;
            }

            // 2. 匹配游戏配置
            GameConfig cfg = null;
            foreach (var kv in _gameConfigs)
            {
                if (title.Contains(kv.Key, StringComparison.OrdinalIgnoreCase))
                {
                    cfg = kv.Value;
                    break;
                }
            }

            if (cfg == null)
            {
                System.Windows.MessageBox.Show($"暂不支持游戏：{title}\n请在 games.json 添加条目。", "提示", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            string url;
            string input = null;
            if (!cfg.NeedsSearch)
            {
                // 直接打开 baseUrl
                url = cfg.BaseUrl;
            }
            else
            {
                // 弹出半透明的搜索框（使用你之前的 Prompt）
                input = await Prompt.ShowDialogAsync("输入关键词…");
                if (string.IsNullOrWhiteSpace(input)) return;

                if (input == "<<LAST>>")
                {
                    if (_currentContentPopup != null)
                    {
                        _currentContentPopup.Activate();
                        return;
                    }
                    if (string.IsNullOrEmpty(_lastUrl))
                    {
                        System.Windows.MessageBox.Show("没有上次搜索记录。");
                        return;
                    }
                    url = _lastUrl;
                }
                else if (cfg.KeywordMap != null && cfg.KeywordMap.TryGetValue(input, out var mappedId))
                {
                    // 用映射到的 ID
                    url = cfg.SearchTemplate
                             .Replace("{baseUrl}", cfg.BaseUrl)
                             .Replace("{id}", mappedId);
                }
                else
                {
                    // 用模板生成 URL
                    string esc = Uri.EscapeDataString(input);
                    url = cfg.SearchTemplate
                        .Replace("{baseUrl}", cfg.BaseUrl)
                        .Replace("{keyword}", esc); 
                }
            }
            // 只有当这是一次“新”搜索或直接打开（!<<LAST>>），才替换旧的浮窗
            if (_currentContentPopup != null)
            {
                _currentContentPopup.Close();
                _currentContentPopup = null;
            }


            // 先验证 URL 格式
            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            {
                System.Windows.MessageBox.Show($"无效的 URL：\n{url}", "URI 格式错误", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }

            // 记录上次 URL
            _lastUrl = uri.AbsoluteUri;

            var popup = new Window
            {
                Title = $"Wiki",
                Width = _settings.Popup.Width,
                Height = _settings.Popup.Height,
                Left = _settings.Popup.Left,
                Top = _settings.Popup.Top,
                Topmost = true,
                WindowStartupLocation = WindowStartupLocation.Manual,
                ShowInTaskbar = false
            };

            // 1）准备容器和遮罩
            var container = new Grid();
            var webView = new WebView2 { Visibility = Visibility.Hidden };
            var overlay = new Border
            {
                Background = new SolidColorBrush(System.Windows.Media.Color.FromArgb(180, 255, 255, 255)),
                Child = new TextBlock
                {
                    Text = "正在加载…",
                    FontSize = 16,
                    FontWeight = FontWeights.Bold,
                    HorizontalAlignment = System.Windows.HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center
                }
            };

            container.Children.Add(webView);
            container.Children.Add(overlay);
            popup.Content = container;

            // 2）马上弹窗，让用户有视觉反馈
            popup.Loaded += (_, __) => popup.Activate();
            popup.Show();

            // 3）初始化 WebView2 内核
            await webView.EnsureCoreWebView2Async(_sharedEnvironment);

            // 4）拦截新窗口、开始导航
            webView.CoreWebView2.NewWindowRequested += (s, e) =>
            {
                e.Handled = true;
                webView.CoreWebView2.Navigate(e.Uri);
            };
            webView.CoreWebView2.Navigate(uri.AbsoluteUri);

            // 5）切换遮罩 & 内容可见性
            webView.NavigationStarting += (s, e) =>
            {
                overlay.Visibility = Visibility.Visible;
                webView.Visibility = Visibility.Hidden;
            };
            webView.NavigationCompleted += (s, e) =>
            {
                overlay.Visibility = Visibility.Collapsed;
                webView.Visibility = Visibility.Visible;
            };

            // 关闭时保存最新位置与大小
            popup.Closed += (s, e) =>
            {
                _settings.Popup.Left = popup.Left;
                _settings.Popup.Top = popup.Top;
                _settings.Popup.Width = popup.Width;
                _settings.Popup.Height = popup.Height;
                SaveSettings();
                _currentContentPopup = null;
                if (webView.CoreWebView2 != null)
                {
                    // 停止所有导航和媒体
                    webView.CoreWebView2.Stop();
                    // 强制释放底层资源
                    webView.Dispose();
                }
            };
            _currentContentPopup = popup;
        }

        private void LoadGameConfigs()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "games.json");
            if (!File.Exists(path))
            {
                System.Windows.MessageBox.Show("缺少文件games.json,检查下载是否完全");
                _gameConfigs = new Dictionary<string, GameConfig>(StringComparer.OrdinalIgnoreCase);
                return;
            }

            var doc = JsonDocument.Parse(File.ReadAllText(path));
            _gameConfigs = new Dictionary<string, GameConfig>(StringComparer.OrdinalIgnoreCase);

            foreach (var prop in doc.RootElement.EnumerateObject())
            {
                if (prop.Value.ValueKind == JsonValueKind.Object)
                {
                    var cfg = prop.Value.Deserialize<GameConfig>();
                    // 兼容：如果 searchTemplate 为空，就用默认 "{baseUrl}/{keyword}"
                    if (cfg.NeedsSearch && string.IsNullOrWhiteSpace(cfg.SearchTemplate))
                        cfg.SearchTemplate = "{baseUrl}/{keyword}";
                    _gameConfigs[prop.Name] = cfg;
                }
                else if (prop.Value.ValueKind == JsonValueKind.String)
                {
                    // 向后兼容：简单 string 映射
                    _gameConfigs[prop.Name] = new GameConfig
                    {
                        BaseUrl = prop.Value.GetString(),
                        NeedsSearch = true,
                        SearchTemplate = "{baseUrl}/{keyword}"
                    };
                }
            }
        }

        private string GetActiveWindowTitle()
        {
            var sb = new StringBuilder(512);
            IntPtr hwnd = GetForegroundWindow();
            GetWindowText(hwnd, sb, sb.Capacity);
            return sb.ToString();
        }

        [DllImport("user32.dll")]
        private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();
    }
    //搜索栏
    public static class Prompt
    {
        //是否存在搜索栏
        private static Window _currentPrompt;
        public static Task<string> ShowDialogAsync(string placeholder = "输入关键词…")
        {
            // 如果已有一个没关闭的，就激活它并直接返回 null（等用户自己关闭再下一次打开）
            if (_currentPrompt != null && _currentPrompt.IsVisible)
            {
                _currentPrompt.Activate();
                return null;
            }

            var tcs = new TaskCompletionSource<string>();
            bool lastClicked = false;
            // 1. 新建无边框半透明窗体
            var prompt = new Window
            {
                Width = 400,
                Height = 100,
                WindowStyle = WindowStyle.None,
                AllowsTransparency = true,
                Background = System.Windows.Media.Brushes.Transparent,
                Opacity = 0.75,
                Topmost = true,
                ShowInTaskbar = false,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };

            // 记录到静态字段
            _currentPrompt = prompt;
            // 关闭时清除
            prompt.Closed += (_, __) => _currentPrompt = null;

            // 失去焦点后延迟关闭，避免与DialogResult冲突
            EventHandler deactivatedHandler = null;
            deactivatedHandler = (s, e) =>
            {
                prompt.Deactivated -= deactivatedHandler;
                // 延迟执行Close
                prompt.Dispatcher.BeginInvoke((Action)(() =>
                {
                    if (prompt.IsVisible)
                    {
                        prompt.Close();
                        tcs.TrySetResult(null);
                    }
                }), DispatcherPriority.Background);
            };
            prompt.Deactivated += deactivatedHandler;

            // 当按 Esc 时，直接关闭对话框
            prompt.PreviewKeyDown += (s, e) =>
            {
                if (e.Key == Key.Escape)
                {
                    prompt.Close();
                    tcs.TrySetResult(null);
                }
            };

            // 2. 圆角矩形 + 图标 + 输入框
            var border = new Border
            {
                CornerRadius = new CornerRadius(8),
                Background = System.Windows.Media.Brushes.White,
                Padding = new Thickness(8)
            };

            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            // 放大镜图标（Segoe MDL2 Assets 搜索图标 U+E721）
            var icon = new TextBlock
            {
                FontFamily = new System.Windows.Media.FontFamily("Segoe MDL2 Assets"),
                Text = "\uE721",
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 8, 0)
            };
            Grid.SetColumn(icon, 0);

            // 输入框
            var input = new System.Windows.Controls.TextBox
            {
                Background = System.Windows.Media.Brushes.Transparent,
                BorderThickness = new Thickness(0),
                VerticalContentAlignment = VerticalAlignment.Center,
                FontSize = 14,
                Foreground = System.Windows.Media.Brushes.Black,
                //如果你的 .NET 版本支持 PlaceholderText：
                //PlaceholderText        = placeholder
            };
            Grid.SetColumn(input, 1);

            // 回车提交
            input.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter)
                {
                    prompt.Close();
                    tcs.TrySetResult(input.Text);
                }
                else if (e.Key == Key.Escape)
                {
                    prompt.Close();
                    tcs.TrySetResult(null);
                }
            };

            grid.Children.Add(icon);
            grid.Children.Add(input);
            border.Child = grid;

            // “打开上次搜索内容”按钮
            var lastBtn = new System.Windows.Controls.Button
            {
                Content = "打开上次搜索内容",
                Opacity = 0.9,
                Background = System.Windows.Media.Brushes.White,
                BorderBrush = System.Windows.Media.Brushes.Transparent,
                Height = 30,                      // 挺高一点
                Width = 110,                     // 足够宽
                FontSize = 10,                      // 文本更大
                Padding = new Thickness(10, 5, 10, 5),  // 文本四周留白
                HorizontalAlignment = System.Windows.HorizontalAlignment.Center,
                Margin = new Thickness(0, 4, 0, 0) // 上方留点间距
            };
            lastBtn.Click += (s, e) =>
            {
                lastClicked = true;
                prompt.Close();
                tcs.TrySetResult("<<LAST>>");
            };

            // 布局
            var panel = new StackPanel();
            panel.Children.Add(border);
            panel.Children.Add(lastBtn);
            prompt.Content = panel;

            // 确保获得焦点
            prompt.Loaded += (_, __) =>
            {
                prompt.Activate();
                input.Focus();
            };
            // 弹出 Modeless 窗口
            prompt.Show();

            return tcs.Task;
        }
    }
}
