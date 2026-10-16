/**
 * Interceptor Global de Eventos de Afiliación (Vanilla JS)
 * Ligero, independiente del framework, sin dependencias y con impacto 0 en Web Vitals (INP / CLS / LCP).
 */
export function initAffiliateTracker() {
	if (typeof window === 'undefined' || typeof document === 'undefined') return;
	if (window.__affiliateTrackerInitialized) return;
	window.__affiliateTrackerInitialized = true;

	document.addEventListener(
		'click',
		function (event) {
			const target = event.target;
			if (!target || typeof target.closest !== 'function') return;

			const trackEl = target.closest('[data-track-event]');
			if (!trackEl) return;

			const eventName = trackEl.getAttribute('data-track-event') || 'affiliate_click';
			const store = trackEl.getAttribute('data-store') || 'amazon';
			const slug =
				trackEl.getAttribute('data-slug') ||
				window.location.pathname.replace(/^\/blog\//, '').replace(/\/$/, '') ||
				'home';
			const position = trackEl.getAttribute('data-position') || 'unknown';
			const href = trackEl.getAttribute('href') || (trackEl.tagName === 'A' ? trackEl.href : '');

			const payload = {
				store: store,
				slug: slug,
				position: position,
				url: href,
				path: window.location.pathname,
			};

			// Restricción de rendimiento: Envío 100% asíncrono y no bloqueante.
			// PostHog capture con transport: 'sendBeacon' para delegar el envío al background del navegador.
			if (window.posthog && typeof window.posthog.capture === 'function') {
				try {
					window.posthog.capture(eventName, payload, { transport: 'sendBeacon' });
				} catch (err) {
					// Silencio defensivo: la navegación del usuario jamás se debe interrumpir
				}
			}
		},
		{ capture: true, passive: true }
	);
}

// Auto-inicialización inmediata en el cliente
if (typeof window !== 'undefined') {
	initAffiliateTracker();
}
