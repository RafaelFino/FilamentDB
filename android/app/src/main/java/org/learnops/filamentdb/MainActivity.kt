package org.learnops.filamentdb

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * Container WebView para o FilamentDB.
 *
 * O acesso passa pelo portal do Pangolin (login por email/senha, sessao por
 * cookie). O CookieManager persiste a sessao entre aberturas do app, entao o
 * usuario loga uma vez e nas proximas ja entra direto.
 *
 * Estruturado para evoluir: o WebView e um componente isolado; features nativas
 * futuras (ex: descoberta/integracao com a impressora na LAN) podem ser expostas
 * ao JS via addJavascriptInterface (ver PrinterBridge no fim do arquivo).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        swipeRefresh = findViewById(R.id.swipe_refresh)
        webView = findViewById(R.id.web_view)

        configureWebView()
        configureCookies()
        configureDownloads()
        configureBackNavigation()
        configurePullToRefresh()

        if (savedInstanceState == null) {
            webView.loadUrl(BuildConfig.SERVER_URL)
        } else {
            webView.restoreState(savedInstanceState)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true           // main.js depende disso
            domStorageEnabled = true           // localStorage / sessionStorage
            databaseEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true             // respeita o meta viewport da pagina
            cacheMode = android.webkit.WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = true
        }

        webView.webChromeClient = WebChromeClient()

        webView.webViewClient = object : WebViewClient() {
            // Mantem a navegacao do mesmo host dentro do WebView; abre links
            // externos no navegador do sistema.
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean {
                val url = request.url
                val host = url.host ?: return false
                return if (host.endsWith("learnops.duckdns.org")) {
                    false // deixa o WebView carregar (inclui o portal do Pangolin)
                } else {
                    // Link externo -> navegador do sistema
                    try {
                        startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, url))
                    } catch (_: Exception) {
                        Toast.makeText(this@MainActivity, R.string.err_open_link, Toast.LENGTH_SHORT).show()
                    }
                    true
                }
            }

            override fun onPageFinished(view: WebView, url: String?) {
                swipeRefresh.isRefreshing = false
                // Persiste cookies em disco assim que a pagina carrega.
                CookieManager.getInstance().flush()
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                // So reporta erro do frame principal (ignora sub-recursos).
                if (request.isForMainFrame) {
                    swipeRefresh.isRefreshing = false
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.err_load, error.description),
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }
    }

    private fun configureCookies() {
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true) // portal do Pangolin pode usar
        }
    }

    private fun configureDownloads() {
        // Downloads de perfil (.json/.info) vao para a pasta Downloads do sistema.
        webView.setDownloadListener(DownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            try {
                val request = DownloadManager.Request(Uri.parse(url)).apply {
                    setMimeType(mimeType)
                    // Repassa os cookies de sessao para o download passar pelo Pangolin.
                    val cookie = CookieManager.getInstance().getCookie(url)
                    if (cookie != null) addRequestHeader("cookie", cookie)
                    addRequestHeader("User-Agent", userAgent)
                    setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    val fileName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType)
                    setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, fileName)
                    setTitle(fileName)
                }
                val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)
                Toast.makeText(this, R.string.download_started, Toast.LENGTH_SHORT).show()
            } catch (_: Exception) {
                Toast.makeText(this, R.string.err_download, Toast.LENGTH_SHORT).show()
            }
        })
    }

    private fun configureBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    private fun configurePullToRefresh() {
        swipeRefresh.setOnRefreshListener { webView.reload() }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onDestroy() {
        // Evita leak do WebView.
        (webView.parent as? android.view.ViewGroup)?.removeView(webView)
        webView.destroy()
        super.onDestroy()
    }

    // ---------------------------------------------------------------------
    // Gancho para features nativas futuras (ex: integracao com a impressora).
    // Quando precisar, exponha metodos ao JS assim (dentro de configureWebView):
    //
    //   webView.addJavascriptInterface(PrinterBridge(this), "AndroidPrinter")
    //
    // e no main.js: window.AndroidPrinter?.discover()
    //
    // class PrinterBridge(private val ctx: Context) {
    //     @android.webkit.JavascriptInterface
    //     fun discover(): String { /* mDNS / scan LAN */ return "[]" }
    // }
    // ---------------------------------------------------------------------
}
