"""Comandos de búsqueda y navegación web."""

import subprocess
from urllib.parse import quote_plus
from rich.console import Console

console = Console()

SEARCH_ENGINES = {
    "google":    "https://www.google.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "bing":      "https://www.bing.com/search?q=",
    "github":    "https://github.com/search?q=",
    "youtube":   "https://www.youtube.com/results?search_query=",
}

QUICK_URLS = {
    "github":    "https://github.com",
    "gmail":     "https://mail.google.com",
    "youtube":   "https://youtube.com",
    "notion":    "https://notion.so",
    "chatgpt":   "https://chat.openai.com",
}


class WebCommands:
    def search(self, query: str, engine: str = "google") -> str:
        """
        Abre una búsqueda web y lee en voz alta un resumen del primer resultado.
        Args:
            query:  Texto a buscar
            engine: Motor de búsqueda (google, duckduckgo, bing, github, youtube)
        """
        base_url = SEARCH_ENGINES.get(engine.lower(), SEARCH_ENGINES["google"])
        url = base_url + quote_plus(query)
        console.print(f"[green]🔍 Buscando en {engine}: {query}[/green]")
        self._open_browser(url)
        
        # Saltamos el scraper de voz si es una búsqueda de videos o github
        if engine.lower() in ("youtube", "github"):
            return ""
            
        # Intentar extraer un snippet rápido para leerlo en voz alta (usando DDG Lite por velocidad)
        try:
            import urllib.request, urllib.parse, re
            # kl=es-es fuerza resultados en español en DuckDuckGo
            data = urllib.parse.urlencode({'q': query, 'kl': 'es-es'}).encode('utf-8')
            req = urllib.request.Request(
                'https://lite.duckduckgo.com/lite/',
                data=data,
                headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
                    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
                }
            )
            html = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
            
            snippets = re.findall(r'<td class=\'result-snippet\'[^>]*>(.*?)</td>', html, re.IGNORECASE | re.DOTALL)
            if snippets:
                # Limpiar tags HTML (como <b>, <i>)
                clean_text = re.sub(r'<[^>]+>', '', snippets[0]).strip()
                if len(clean_text) > 20:
                    # Limitar a ~250 caracteres para no cansar al usuario escuchando
                    if len(clean_text) > 250:
                        clean_text = clean_text[:250].rsplit(' ', 1)[0] + "..."
                    return f"Según internet: {clean_text}"
        except Exception as e:
            console.print(f"[dim]No se pudo extraer resumen de voz: {e}[/dim]")
            
        return ""

    def open_url(self, url: str) -> None:
        """
        Abre una URL directa. Primero revisa si es un atajo conocido.
        Args:
            url: URL completa (https://...) o nombre de sitio (github, youtube...)
        """
        # Permitir shortcuts como "github", "youtube", etc.
        resolved = QUICK_URLS.get(url.lower(), url)
        if not resolved.startswith(("http://", "https://")):
            resolved = "https://" + resolved
        console.print(f"[green]🌐 Abriendo: {resolved}[/green]")
        self._open_browser(resolved)

    def _open_browser(self, url: str) -> None:
        """Abre una URL en Firefox (o el navegador por defecto del sistema)."""
        try:
            subprocess.Popen(
                ["firefox", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            # Fallback a xdg-open si Firefox no está instalado
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
