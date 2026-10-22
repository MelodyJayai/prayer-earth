/** Static assets are served before this handler, without an origin dependency.
 * Missing paths and unsupported methods reach this handler. No network fetch,
 * database, administrator API, or application runtime is attached to the site.
 */
export default {
  async fetch(request) {
    const status = request.method === "GET" || request.method === "HEAD" ? 404 : 405;
    const headers = {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    };
    if (status === 405) headers.Allow = "GET, HEAD";
    return new Response(request.method === "HEAD" ? null : status === 404 ? "Not Found" : "Method Not Allowed", {
      status,
      headers,
    });
  },
};
