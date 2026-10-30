"""Gracia adapter: retain the WebView environment until the STA is torn down."""


def adapt(source):
    changes = [
        ('ComPtr<ICoreWebView2Controller> controller;',
         'ComPtr<ICoreWebView2Environment> browserEnvironment;\nComPtr<ICoreWebView2Controller> controller;'),
        ('HRESULT h = environment->CreateCoreWebView2Controller(host.load(),',
         'browserEnvironment = environment; // Keep the asynchronous creation owner alive.\n'
         '                { std::ofstream log(directory / L"web-texture.log", std::ios::app);\n'
         '                  log << "Environment retained; creating controller, tick=" << GetTickCount64() << "\\n"; }\n'
         '                HRESULT h = browserEnvironment->CreateCoreWebView2Controller(host.load(),'),
        ('controller = value;',
         'controller = value;\n'
         '                             { std::ofstream log(directory / L"web-texture.log", std::ios::app);\n'
         '                               log << "Controller ready, tick=" << GetTickCount64() << "\\n"; }'),
        ('web.Reset(); controller.Reset();', 'web.Reset(); controller.Reset(); browserEnvironment.Reset();'),
        ('web.Detach(); controller.Detach();', 'web.Detach(); controller.Detach(); browserEnvironment.Detach();'),
    ]
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError('WebView lifetime adapter source drift: ' + old)
        source = source.replace(old, new)
    return source
