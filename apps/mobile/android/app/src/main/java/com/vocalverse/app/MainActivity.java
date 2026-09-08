package com.vocalverse.app;

import android.os.Bundle;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;

/**
 * Android 返回手势/返回键接管（2026-09-10 修复「手机端手势滑动返回直接退到手机桌面」）。
 *
 * 背景：Capacitor 8 的 BridgeActivity 自身不处理返回（core 内无 onBackPressed/canGoBack 逻辑），
 * 且本工程 targetSdk = 36（Android 16 起对 targetSdk 36 的应用默认启用预测式返回 predictive back）
 * ——只重写已废弃的 onBackPressed() 在 Android 16 设备上收不到回调，
 * 因此统一走 AndroidX OnBackPressedDispatcher 注册回调（同时覆盖返回键与 13+ 返回手势）。
 *
 * 处理顺序（与 Android 通用习惯一致）：
 *   1. 页面弹层优先：调 window.__vvNativeBack()（web 侧 composables/useNativeBack.ts 注册，
 *      如阅读器目录/设置/词卡/批注弹层、全局账户抽屉）——返回 true 表示已消费，本次返回结束；
 *   2. 否则回退 WebView 历史（SPA 由 vue-router 的 popstate 接管，即回到上一个页面）；
 *   3. 历史到底（App 首页）→ finish() 结束 Activity，回到桌面（与系统返回一致）。
 *
 * 注意：web 侧改动（server.url 远程壳）无需重装 APK；本文件属原生层，必须重新 assembleDebug 装包。
 */
public class MainActivity extends BridgeActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getOnBackPressedDispatcher().addCallback(
            this,
            new OnBackPressedCallback(true) {
                @Override
                public void handleOnBackPressed() {
                    WebView webView = getCapacitorWebView();
                    if (webView == null) {
                        finish();
                        return;
                    }
                    // 先问页面：弹层/抽屉是否消费本次返回（关弹层 → 不回退页面）
                    webView.evaluateJavascript(
                        "(function(){try{return window.__vvNativeBack ? window.__vvNativeBack() === true : false}catch(e){return false}})()",
                        value -> {
                            if ("true".equals(value)) {
                                return;
                            }
                            if (webView.canGoBack()) {
                                webView.goBack();
                            } else {
                                finish();
                            }
                        }
                    );
                }
            }
        );
    }

    private WebView getCapacitorWebView() {
        Bridge bridge = getBridge();
        return bridge == null ? null : bridge.getWebView();
    }
}
