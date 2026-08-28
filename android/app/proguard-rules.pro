# Mantem nomes de classes/metodos anotados com @JavascriptInterface,
# necessario quando (futuramente) houver bridge JS <-> Kotlin.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
