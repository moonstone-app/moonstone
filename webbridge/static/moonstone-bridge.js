/**
 * MoonstoneBridge — JavaScript client library for the WebBridge plugin API.
 *
 * Usage:
 *   const moonstone = new MoonstoneBridge('http://localhost:8090');
 *   const page = await moonstone.getPage('MyPage');
 *   await moonstone.savePage('MyPage', 'Content here', 'wiki');
 *
 * Events (via SSE):
 *   moonstone.on('page-changed', (data) => console.log('Page changed:', data.page));
 *   moonstone.on('page-saved', (data) => console.log('Page saved:', data.page));
 */
class MoonstoneBridge {

	/**
	 * @param {string} [baseUrl] — Base URL of the WebBridge server.
	 *   Defaults to the current origin (works when loaded from the server itself).
	 * @param {object} [options]
	 * @param {string} [options.authToken] — Authentication token (if configured).
	 * @param {boolean} [options.autoConnect=true] — Auto-connect to SSE stream.
	 */
	constructor(baseUrl, options = {}) {
		this.baseUrl = (baseUrl || window.location.origin).replace(/\/$/, '');
		this.authToken = options.authToken || null;
		this._listeners = {};
		this._eventSource = null;

		if (options.autoConnect !== false) {
			this.connect();
		}
	}

	// ============================================================
	// HTTP helpers
	// ============================================================

	_headers() {
		const h = { 'Content-Type': 'application/json' };
		if (this.authToken) h['X-Auth-Token'] = this.authToken;
		return h;
	}

	async _request(method, path, body) {
		const url = this.baseUrl + path;
		const opts = { method, headers: this._headers() };
		if (body !== undefined) opts.body = JSON.stringify(body);
		const resp = await fetch(url, opts);
		if (!resp.ok) {
			const err = await resp.json().catch(() => ({ error: resp.statusText }));
			throw new MoonstoneBridgeError(err.error || 'Request failed', resp.status, err);
		}
		return resp.json();
	}

	async _get(path) { return this._request('GET', path); }
	async _put(path, body) { return this._request('PUT', path, body); }
	async _post(path, body) { return this._request('POST', path, body); }
	async _delete(path) { return this._request('DELETE', path); }

	/**
	 * Encode a page path for use in URLs.
	 * Splits on ':' and encodes each segment individually,
	 * so non-ASCII characters (Russian, CJK, etc.) work correctly.
	 * @param {string} pagePath — e.g. 'Namespace:Субстраница'
	 * @returns {string} — e.g. 'Namespace/%D0%A1%D1%83%D0%B1...'
	 */
	_encodePath(pagePath) {
		return pagePath.split(':').map(s => encodeURIComponent(s)).join('/');
	}

	// ============================================================
	// Notebook info
	// ============================================================

	/** Get notebook metadata. */
	async getNotebook() {
		return this._get('/api/notebook');
	}

	/** Get the currently active page. */
	async getCurrentPage() {
		return this._get('/api/current');
	}

	// ============================================================
	// Pages
	// ============================================================

    /**
     * Get a specific page by path.
     * @param {string} pagePath — e.g. 'Namespace:Subpage'
     * @returns {Promise<Object>} Page object
     */
	async listPages(namespace, options = {}) {
		const parts = [];
		if (namespace) parts.push('namespace=' + encodeURIComponent(namespace));
		if (options.limit != null) parts.push('limit=' + options.limit);
		if (options.offset != null) parts.push('offset=' + options.offset);
		const qs = parts.length ? '?' + parts.join('&') : '';
		return this._get('/api/pages' + qs);
	}

	/**
	 * Get page content.
	 * @param {string} pagePath — Page name (e.g. 'MyPage' or 'Namespace:SubPage').
	 * @param {string} [format='wiki'] — Output format: 'wiki', 'html', or 'plain'.
	 * @returns {Promise<{name, basename, title, content, format, exists, haschildren}>}
	 */
	async getPage(pagePath, format = 'wiki') {
		const p = this._encodePath(pagePath);
		const qs = format !== 'wiki' ? '?format=' + format : '';
		return this._get('/api/page/' + p + qs);
	}

	/**
	 * Save (overwrite) a page.
	 * @param {string} pagePath — Page name.
	 * @param {string} content — Page content.
	 * @param {string} [format='wiki'] — Content format.
	 * @returns {Promise<{ok: boolean, page: string}>}
	 */
	async savePage(pagePath, content, format = 'wiki', expectedMtime = null) {
		const body = { content, format };
		if (expectedMtime !== null) body.expected_mtime = expectedMtime;
		return this._put('/api/page/' + this._encodePath(pagePath), body);
	}

	/**
	 * Create a new page (fails if exists).
	 * @param {string} pagePath — Page name.
	 * @param {string} [content=''] — Initial content.
	 * @param {string} [format='wiki'] — Content format.
	 * @returns {Promise<{ok: boolean, page: string}>}
	 */
	async createPage(pagePath, content = '', format = 'wiki') {
		return this._post('/api/page/' + this._encodePath(pagePath), { content, format });
	}

	/**
	 * Delete a page.
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{ok: boolean, deleted: string}>}
	 */
	async deletePage(pagePath) {
		return this._delete('/api/page/' + this._encodePath(pagePath));
	}

	// ============================================================
	// Tags
	// ============================================================

	/**
	 * List all tags in the notebook.
	 * @returns {Promise<{tags: Array<{name, count}>, count: number}>}
	 */
	async listTags() {
		return this._get('/api/tags');
	}

	/**
	 * Get pages with a specific tag.
	 * @param {string} tag — Tag name (without @).
	 * @returns {Promise<{tag, pages: Array<{name, basename}>, count}>}
	 */
	async getTagPages(tag) {
		return this._get('/api/tags/' + encodeURIComponent(tag) + '/pages');
	}

	/**
	 * Get tags for a specific page.
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{page, tags: Array<{name}>}>}
	 */
	async getPageTags(pagePath) {
		return this._get('/api/page/' + this._encodePath(pagePath) + '/tags');
	}

	// ============================================================
	// Links / Backlinks
	// ============================================================

	/**
	 * Get links for a page.
	 * @param {string} pagePath — Page name.
	 * @param {string} [direction='forward'] — 'forward', 'backward', or 'both'.
	 * @returns {Promise<{page, direction, links: Array<{source, target}>, count}>}
	 */
	async getLinks(pagePath, direction = 'forward') {
		const qs = direction !== 'forward' ? '?direction=' + direction : '';
		return this._get('/api/links/' + this._encodePath(pagePath) + qs);
	}

	/**
	 * Get backlinks (pages linking TO this page).
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{page, direction, links: Array<{source, target}>, count}>}
	 */
	async getBacklinks(pagePath) {
		return this.getLinks(pagePath, 'backward');
	}

	// ============================================================
	// Recent Changes
	// ============================================================

	/**
	 * Get recently changed pages.
	 * @param {number} [limit=20] — Max number of results.
	 * @param {number} [offset=0] — Offset for pagination.
	 * @returns {Promise<{pages: Array<{name, basename, mtime, haschildren, hascontent}>, limit, offset}>}
	 */
	async getRecentChanges(limit = 20, offset = 0) {
		return this._get('/api/recent?limit=' + limit + '&offset=' + offset);
	}

	// ============================================================
	// Navigation
	// ============================================================

	/**
	 * Request navigation to a specific page in the GUI.
	 * @param {string} pagePath — Page name to open.
	 * @returns {Promise<{ok: boolean, page: string}>}
	 */
	async navigateTo(pagePath) {
		return this._post('/api/navigate', { page: pagePath });
	}

	// ============================================================
	// Autocomplete / Match
	// ============================================================

	/**
	 * Fuzzy match page names (for autocomplete).
	 * @param {string} query — Partial page name.
	 * @param {number} [limit=10] — Max results.
	 * @returns {Promise<{query, pages: Array<{name, basename}>}>}
	 */
	async matchPages(query, limit = 10) {
		return this._get('/api/pages/match?q=' + encodeURIComponent(query) + '&limit=' + limit);
	}

	// ============================================================
	// Stats
	// ============================================================

	/**
	 * Get notebook statistics.
	 * @returns {Promise<{pages: number, tags: number}>}
	 */
	async getStats() {
		return this._get('/api/stats');
	}

	// ============================================================
	// Page operations
	// ============================================================

	/**
	 * Append content to a page (without overwriting).
	 * @param {string} pagePath — Page name.
	 * @param {string} content — Content to append.
	 * @param {string} [format='wiki'] — Content format.
	 * @returns {Promise<{ok: boolean, page: string}>}
	 */
	async appendToPage(pagePath, content, format = 'wiki') {
		return this._post('/api/page/' + this._encodePath(pagePath) + '/append', { content, format });
	}

	/**
	 * Move/rename a page.
	 * @param {string} pagePath — Current page name.
	 * @param {string} newPath — New page name.
	 * @param {boolean} [updateLinks=true] — Update links in other pages.
	 * @returns {Promise<{ok: boolean, old: string, new: string}>}
	 */
	async movePage(pagePath, newPath, updateLinks = true) {
		return this._post('/api/page/' + this._encodePath(pagePath) + '/move', {
			newpath: newPath, update_links: updateLinks
		});
	}

	/**
	 * Delete an attachment.
	 * @param {string} pagePath — Page name.
	 * @param {string} filename — Attachment filename.
	 * @returns {Promise<{ok, page, deleted}>}
	 */
	async deleteAttachment(pagePath, filename) {
		return this._delete('/api/attachment/' +
			this._encodePath(pagePath) + '?filename=' + encodeURIComponent(filename));
	}

	// ============================================================
	// Page tree
	// ============================================================

	/**
	 * Get hierarchical page tree.
	 * @param {string} [namespace] — Root namespace.
	 * @param {number} [depth=2] — Depth of tree.
	 * @returns {Promise<{tree: Array, namespace: string}>}
	 */
	async getPageTree(namespace, depth = 2) {
		let qs = '?depth=' + depth;
		if (namespace) qs += '&namespace=' + encodeURIComponent(namespace);
		return this._get('/api/pagetree' + qs);
	}

	// ============================================================
	// Search
	// ============================================================

	/**
	 * Search pages.
	 * @param {string} query — Search query.
	 * @returns {Promise<{query, results: Array, count: number}>}
	 */
	async search(query, options = {}) {
		let qs = '?q=' + encodeURIComponent(query);
		if (options.snippets) qs += '&snippets=true';
		if (options.snippetLength) qs += '&snippet_length=' + options.snippetLength;
		return this._get('/api/search' + qs);
	}

	// ============================================================
	// Attachments
	// ============================================================

	/**
	 * List attachments for a page.
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{page, attachments: Array<{name, size, mtime}>}>}
	 */
	async listAttachments(pagePath) {
		return this._get('/api/attachments/' + this._encodePath(pagePath));
	}

	/**
	 * Get the URL for an attachment (for use in <img src>, etc.).
	 * @param {string} pagePath — Page name.
	 * @param {string} filename — Attachment filename.
	 * @returns {string}
	 */
	getAttachmentUrl(pagePath, filename) {
		let url = this.baseUrl + '/api/attachment/' +
			this._encodePath(pagePath) + '?filename=' + encodeURIComponent(filename);
		if (this.authToken) url += '&token=' + encodeURIComponent(this.authToken);
		return url;
	}

	/**
	 * Upload an attachment.
	 * @param {string} pagePath — Page name.
	 * @param {string} filename — Filename.
	 * @param {Blob|ArrayBuffer|Uint8Array} data — File data.
	 * @returns {Promise<{ok, page, filename}>}
	 */
	async uploadAttachment(pagePath, filename, data) {
		const url = this.baseUrl + '/api/attachment/' +
			this._encodePath(pagePath) + '?filename=' + encodeURIComponent(filename);
		const headers = {};
		if (this.authToken) headers['X-Auth-Token'] = this.authToken;
		const resp = await fetch(url, { method: 'POST', headers, body: data });
		if (!resp.ok) {
			const err = await resp.json().catch(() => ({ error: resp.statusText }));
			throw new MoonstoneBridgeError(err.error || 'Upload failed', resp.status, err);
		}
		return resp.json();
	}

	// ============================================================
	// Applets
	// ============================================================

	/** List available applets. */
	async listApplets() {
		return this._get('/api/applets');
	}

	// ============================================================
	// Walk (recursive page listing)
	// ============================================================

	/**
	 * Recursively list all pages under a namespace.
	 * @param {string} [namespace] — Root namespace (empty = all).
	 * @returns {Promise<{pages: Array, namespace: string, count: number}>}
	 */
	async walkPages(namespace) {
		const qs = namespace ? '?namespace=' + encodeURIComponent(namespace) : '';
		return this._get('/api/pages/walk' + qs);
	}

	// ============================================================
	// Siblings (previous / next)
	// ============================================================

	/**
	 * Get previous and next sibling pages.
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{page, previous, next}>}
	 */
	async getSiblings(pagePath) {
		return this._get('/api/page/' + this._encodePath(pagePath) + '/siblings');
	}

	// ============================================================
	// Trash (safe delete)
	// ============================================================

	/**
	 * Move a page to trash (safe delete).
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{ok: boolean, trashed: string}>}
	 */
	async trashPage(pagePath) {
		return this._post('/api/page/' + this._encodePath(pagePath) + '/trash');
	}

	// ============================================================
	// Links Section (namespace-wide)
	// ============================================================

	/**
	 * Get links for an entire namespace section.
	 * @param {string} pagePath — Namespace root page.
	 * @param {string} [direction='forward'] — 'forward', 'backward', or 'both'.
	 * @returns {Promise<{page, direction, links: Array, count}>}
	 */
	async getLinksSection(pagePath, direction = 'forward') {
		const qs = direction !== 'forward' ? '?direction=' + direction : '';
		return this._get('/api/links/' + this._encodePath(pagePath) + '/section' + qs);
	}

	// ============================================================
	// Intersecting Tags (faceted navigation)
	// ============================================================

	/**
	 * Find tags that co-occur with the given tags.
	 * @param {string[]} tags — Array of tag names.
	 * @returns {Promise<{query_tags, intersecting: Array<{name, count}>, count}>}
	 */
	async getIntersectingTags(tags) {
		return this._get('/api/tags/intersecting?tags=' + encodeURIComponent(tags.join(',')));
	}

	// ============================================================
	// Resolve / Create Links
	// ============================================================

	/**
	 * Resolve a wiki link from a source page context.
	 * @param {string} source — Source page name.
	 * @param {string} link — Wiki link text (e.g. ':Page:Sub' or '+Child').
	 * @returns {Promise<{source, link, resolved}>}
	 */
	async resolveLink(source, link) {
		return this._post('/api/resolve-link', { source, link });
	}

	/**
	 * Create a proper wiki link between two pages.
	 * @param {string} source — Source page name.
	 * @param {string} target — Target page name.
	 * @returns {Promise<{source, target, href}>}
	 */
	async createLink(source, target) {
		return this._post('/api/create-link', { source, target });
	}

	// ============================================================
	// Suggest Link
	// ============================================================

	/**
	 * Get link suggestions (autocomplete).
	 * @param {string} text — Text to match.
	 * @param {string} [from='Home'] — Source page context.
	 * @returns {Promise<{source, text, suggestions: Array<{name}>}>}
	 */
	async suggestLink(text, from = 'Home') {
		return this._get('/api/suggest-link?text=' + encodeURIComponent(text) +
			'&from=' + encodeURIComponent(from));
	}

	// ============================================================
	// KV Store (per-applet persistent storage)
	// ============================================================

	/**
	 * Get a stored value for an applet.
	 * @param {string} applet — Applet name.
	 * @param {string} key — Key name.
	 * @returns {Promise<{applet, key, value}>}
	 */
	async storeGet(applet, key) {
		return this._get('/api/store/' + encodeURIComponent(applet) + '/' + encodeURIComponent(key));
	}

	/**
	 * Save a value for an applet.
	 * @param {string} applet — Applet name.
	 * @param {string} key — Key name.
	 * @param {*} value — Any JSON-serializable value.
	 * @returns {Promise<{ok, applet, key}>}
	 */
	async storePut(applet, key, value) {
		return this._put('/api/store/' + encodeURIComponent(applet) + '/' + encodeURIComponent(key),
			{ value });
	}

	/**
	 * Delete a stored key for an applet.
	 * @param {string} applet — Applet name.
	 * @param {string} key — Key name.
	 * @returns {Promise<{ok, applet, deleted}>}
	 */
	async storeDelete(applet, key) {
		return this._delete('/api/store/' + encodeURIComponent(applet) + '/' + encodeURIComponent(key));
	}

	/**
	 * List all stored keys for an applet.
	 * @param {string} applet — Applet name.
	 * @returns {Promise<{applet, keys: string[]}>}
	 */
	async storeKeys(applet) {
		return this._get('/api/store/' + encodeURIComponent(applet));
	}

	// ============================================================
	// Batch Operations
	// ============================================================

	/**
	 * Execute multiple API operations in one request.
	 * @param {Array<{method, path, body?}>} operations — Array of operations.
	 * @returns {Promise<{results: Array<{index, status, body}>, count}>}
	 */
	async batch(operations) {
		return this._post('/api/batch', operations);
	}

	// ============================================================
	// Parse Tree
	// ============================================================

	/**
	 * Get the structured parse tree for a page as JSON.
	 * @param {string} pagePath — Page name.
	 * @returns {Promise<{name, tree: object, exists: boolean}>}
	 */
	async getParseTree(pagePath) {
		return this._get('/api/page/' + this._encodePath(pagePath) + '/parsetree');
	}

	// ============================================================
	// Custom Events (Applet-to-Applet messaging)
	// ============================================================

	// ============================================================
	// v2.2 — New API Methods
	// ============================================================

	/**
	 * Partially update page content using search/replace operations.
	 * @param {string} pagePath — Page name.
	 * @param {Array<{op, search, replace?, content?}>} operations — Patch ops.
	 * @param {number} [expectedMtime] — For optimistic concurrency.
	 * @returns {Promise<{ok, page, mtime, operations}>}
	 */
	async patchPage(pagePath, operations, expectedMtime = null) {
		const body = { operations };
		if (expectedMtime !== null) body.expected_mtime = expectedMtime;
		return this._request('PATCH', '/api/page/' + this._encodePath(pagePath), body);
	}

	/**
	 * List available export/dump formats.
	 * @returns {Promise<{formats: string[]}>}
	 */
	async listFormats() {
		return this._get('/api/formats');
	}

	/**
	 * Count pages without loading them.
	 * @param {string} [namespace] — Namespace to count in.
	 * @returns {Promise<{count: number, namespace: string}>}
	 */
	async countPages(namespace) {
		const qs = namespace ? '?namespace=' + encodeURIComponent(namespace) : '';
		return this._get('/api/pages/count' + qs);
	}

	/**
	 * Count links for a page without loading.
	 * @param {string} pagePath — Page name.
	 * @param {string} [direction='forward'] — Link direction.
	 * @returns {Promise<{page, direction, count}>}
	 */
	async countLinks(pagePath, direction = 'forward') {
		const qs = direction !== 'forward' ? '?direction=' + direction : '';
		return this._get('/api/links/' + this._encodePath(pagePath) + '/count' + qs);
	}

	/**
	 * List floating (ambiguous) links in the notebook.
	 * @returns {Promise<{links: Array<{source, target}>, count}>}
	 */
	async listFloatingLinks() {
		return this._get('/api/links/floating');
	}

	/**
	 * Get navigation history.
	 * @param {number} [limit=50] — Max entries.
	 * @returns {Promise<{history: Array, recent: Array}>}
	 */
	async getHistory(limit = 50) {
		return this._get('/api/history?limit=' + limit);
	}

	/**
	 * Get applet configuration.
	 * @param {string} appletName — Applet name.
	 * @returns {Promise<{applet, config, schema}>}
	 */
	async getAppletConfig(appletName) {
		return this._get('/api/applets/' + encodeURIComponent(appletName) + '/config');
	}

	/**
	 * Save applet configuration.
	 * @param {string} appletName — Applet name.
	 * @param {object} config — Configuration object.
	 * @returns {Promise<{ok, applet}>}
	 */
	async saveAppletConfig(appletName, config) {
		return this._put('/api/applets/' + encodeURIComponent(appletName) + '/config', config);
	}

	/**
	 * Emit a custom event to all connected applets via SSE.
	 * @param {string} eventType — Custom event name (will be prefixed with 'custom:').
	 * @param {object} [data={}] — Event data.
	 * @returns {Promise<{ok, event}>}
	 */
	async emitEvent(eventType, data = {}) {
		return this._post('/api/emit', { event: eventType, data });
	}

	// ============================================================
	// Server-Sent Events (SSE)
	// ============================================================

	/**
	 * Connect to the SSE event stream.
	 * @param {object} [options]
	 * @param {string[]} [options.subscribe] — Event types to filter (null = all).
	 */
	connect(options = {}) {
		if (this._eventSource) this.disconnect();

		let url = this.baseUrl + '/events';
		const qsParts = [];
		if (this.authToken) qsParts.push('token=' + encodeURIComponent(this.authToken));
		if (options.subscribe) qsParts.push('subscribe=' + encodeURIComponent(options.subscribe.join(',')));
		if (qsParts.length) url += '?' + qsParts.join('&');

		this._eventSource = new EventSource(url);

		// Listen for all known event types
		const knownEvents = [
			'connected', 'page-changed', 'page-saved',
			'page-moved', 'page-deleted', 'store-changed',
		];
		knownEvents.forEach(type => {
			this._eventSource.addEventListener(type, (e) => {
				this._emit(type, JSON.parse(e.data));
			});
		});

		// Listen for custom events (prefixed with 'custom:')
		this._eventSource.onmessage = (e) => {
			try {
				const data = JSON.parse(e.data);
				if (data && data.type && data.type.startsWith('custom:')) {
					this._emit(data.type, data);
				}
			} catch(err) {}
		};

		this._eventSource.onerror = (e) => {
			this._emit('error', { message: 'SSE connection error' });
		};
	}

	/** Disconnect from the SSE event stream. */
	disconnect() {
		if (this._eventSource) {
			this._eventSource.close();
			this._eventSource = null;
		}
	}

	/**
	 * Register an event listener.
	 * @param {string} event — Event name: 'connected', 'page-changed', 'page-saved', 'error'.
	 * @param {function} callback — Callback function receiving the event data.
	 * @returns {MoonstoneBridge} — For chaining.
	 */
	on(event, callback) {
		if (!this._listeners[event]) this._listeners[event] = [];
		this._listeners[event].push(callback);
		return this;
	}

	/**
	 * Remove an event listener.
	 * @param {string} event — Event name.
	 * @param {function} callback — The callback to remove.
	 * @returns {MoonstoneBridge} — For chaining.
	 */
	off(event, callback) {
		if (this._listeners[event]) {
			this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
		}
		return this;
	}

	/** Convenience: listen for page changes. */
	onPageChanged(callback) { return this.on('page-changed', callback); }

	/** Convenience: listen for page saves. */
	onPageSaved(callback) { return this.on('page-saved', callback); }

	_emit(event, data) {
		const cbs = this._listeners[event];
		if (cbs) cbs.forEach(cb => { try { cb(data); } catch (e) { console.error(e); } });
	}

	// ============================================================
	// WebSocket integration (auto-discovery)
	// ============================================================

	/**
	 * Connect to WebSocket server with auto-discovery via /api/capabilities.
	 * @param {object} [options] — Options passed to MoonstoneBridgeWS constructor.
	 * @returns {Promise<MoonstoneBridgeWS>} — The connected WS client.
	 */
	async connectWS(options = {}) {
		if (this._ws) this.disconnectWS();
		const caps = await this._get('/api/capabilities');
		const wsInfo = caps.websocket;
		if (!wsInfo || !wsInfo.enabled || (!wsInfo.url && !wsInfo.port)) {
			throw new MoonstoneBridgeError('WebSocket not available on server', 0, caps);
		}
		// Derive WS URL from the current page hostname + WS port.
		// This ensures LAN devices connect to the correct host
		// (e.g. ws://192.168.1.100:8091 instead of ws://localhost:8091).
		let wsUrl;
		if (wsInfo.port) {
			const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			wsUrl = proto + '//' + window.location.hostname + ':' + wsInfo.port;
		} else {
			wsUrl = wsInfo.url;
		}
		const wsOpts = Object.assign({ token: this.authToken, autoConnect: true }, options);
		this._ws = new MoonstoneBridgeWS(wsUrl, wsOpts);
		return this._ws;
	}

	/** Disconnect WebSocket. */
	disconnectWS() {
		if (this._ws) { this._ws.close(); this._ws = null; }
	}

	/** Whether WS is connected. */
	get wsReady() { return this._ws && this._ws.connected; }

	/** Subscribe to a WS channel. */
	wsSubscribe(channel) { if (!this._ws) throw new Error('WS not connected'); return this._ws.subscribe(channel); }

	/** Unsubscribe from a WS channel. */
	wsUnsubscribe(channel) { if (!this._ws) throw new Error('WS not connected'); return this._ws.unsubscribe(channel); }

	/** Broadcast data to a WS channel. */
	wsBroadcast(channel, data) { if (!this._ws) throw new Error('WS not connected'); return this._ws.broadcast(channel, data); }

	/** Call API through WebSocket. */
	wsApi(method, path, body) { if (!this._ws) throw new Error('WS not connected'); return this._ws.api(method, path, body); }

	/** Listen for events on a WS channel. */
	onChannel(channel, cb) { if (!this._ws) throw new Error('WS not connected'); return this._ws.on('broadcast:' + channel, (msg) => cb(msg.data, msg)); }

	// ============================================================
	// Utilities
	// ============================================================

	/**
	 * Simple wiki text to HTML converter (basic subset).
	 * For full rendering, use format='html' in getPage().
	 */
	static wikiToHtml(text) {
		if (!text) return '';
		let html = text
			// Headings
			.replace(/^={6}\s*(.+?)\s*={6}\s*$/gm, '<h6>$1</h6>')
			.replace(/^={5}\s*(.+?)\s*={5}\s*$/gm, '<h5>$1</h5>')
			.replace(/^={4}\s*(.+?)\s*={4}\s*$/gm, '<h4>$1</h4>')
			.replace(/^={3}\s*(.+?)\s*={3}\s*$/gm, '<h3>$1</h3>')
			.replace(/^={2}\s*(.+?)\s*={2}\s*$/gm, '<h2>$1</h2>')
			// Bold, italic, strikethrough, code
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\/\/(.+?)\/\//g, '<em>$1</em>')
			.replace(/~~(.+?)~~/g, '<del>$1</del>')
			.replace(/''(.+?)''/g, '<code>$1</code>')
			// Links
			.replace(/\[\[(.+?)\|(.+?)\]\]/g, '<a href="#$1">$2</a>')
			.replace(/\[\[(.+?)\]\]/g, '<a href="#$1">$1</a>')
			// Checkboxes
			.replace(/^\[[ ]\]/gm, '☐')
			.replace(/^\[x\]/gm, '☑')
			.replace(/^\[\*\]/gm, '☒')
			// Bullets
			.replace(/^\* /gm, '• ')
			// Line breaks
			.replace(/\n/g, '<br>\n');
		return html;
	}
}


/**
 * WebSocket client for Moonstone real-time communication.
 * Provides channel-based pub/sub, broadcasting, and proxied API calls.
 *
 * Usage:
 *   const ws = new MoonstoneBridgeWS('ws://localhost:8091');
 *   ws.on('connected', (data) => console.log('Connected:', data.client_id));
 *   ws.subscribe('my-channel');
 *   ws.on('broadcast', (msg) => { if (msg.channel === 'my-channel') ... });
 *   ws.broadcast('my-channel', { text: 'hello' });
 *   ws.api('GET', '/api/notebook').then(data => console.log(data));
 *   ws.close();
 */
class MoonstoneBridgeWS {
	constructor(url, options = {}) {
		this._url = url;
		this._token = options.token || null;
		this._autoReconnect = options.autoReconnect !== false;
		this._reconnectDelay = options.reconnectDelay || 2000;
		this._maxReconnectDelay = options.maxReconnectDelay || 30000;
		this._currentDelay = this._reconnectDelay;
		this._ws = null;
		this._listeners = {};
		this._pending = {};
		this._msgId = 0;
		this._closed = false;
		this._clientId = null;
		if (options.autoConnect !== false) this.open();
	}

	open() {
		if (this._ws) return;
		this._closed = false;
		let wsUrl = this._url;
		if (this._token) wsUrl += (wsUrl.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(this._token);
		this._ws = new WebSocket(wsUrl);
		this._ws.onopen = () => { this._currentDelay = this._reconnectDelay; this._emit('open'); };
		this._ws.onmessage = (evt) => { try { this._handleMessage(JSON.parse(evt.data)); } catch(e) {} };
		this._ws.onclose = () => {
			this._ws = null; this._emit('close');
			if (this._autoReconnect && !this._closed) {
				setTimeout(() => this.open(), this._currentDelay);
				this._currentDelay = Math.min(this._currentDelay * 1.5, this._maxReconnectDelay);
			}
		};
		this._ws.onerror = (err) => this._emit('error', err);
	}

	close() {
		this._closed = true; this._autoReconnect = false;
		if (this._ws) { this._ws.close(); this._ws = null; }
		for (const id of Object.keys(this._pending)) {
			this._pending[id].reject(new Error('WebSocket closed'));
			clearTimeout(this._pending[id].timer);
		}
		this._pending = {};
	}

	get connected() { return this._ws && this._ws.readyState === WebSocket.OPEN; }
	get clientId() { return this._clientId; }

	on(event, fn) { if (!this._listeners[event]) this._listeners[event] = []; this._listeners[event].push(fn); return this; }
	off(event, fn) { const a = this._listeners[event]; if (a) this._listeners[event] = a.filter(f => f !== fn); return this; }
	_emit(event, data) { for (const fn of (this._listeners[event] || [])) { try { fn(data); } catch(e) {} } }

	_send(obj) { if (!this.connected) throw new Error('WebSocket not connected'); this._ws.send(JSON.stringify(obj)); }

	_sendWithReply(obj, timeout = 10000) {
		return new Promise((resolve, reject) => {
			const id = ++this._msgId; obj.id = id;
			const timer = setTimeout(() => { delete this._pending[id]; reject(new Error('Timeout')); }, timeout);
			this._pending[id] = { resolve, reject, timer };
			this._send(obj);
		});
	}

	_handleMessage(msg) {
		if (msg.id && this._pending[msg.id]) {
			const p = this._pending[msg.id]; clearTimeout(p.timer); delete this._pending[msg.id];
			msg.ok ? p.resolve(msg.data || msg) : p.reject(new Error(msg.error || 'Failed'));
			return;
		}
		if (msg.event === 'connected') { this._clientId = msg.data && msg.data.client_id; this._emit('connected', msg.data); }
		else if (msg.event === 'broadcast') { this._emit('broadcast', msg); this._emit('broadcast:' + msg.channel, msg); }
		else if (msg.event) { this._emit(msg.event, msg.data || msg); }
	}

	subscribe(channel) { return this._sendWithReply({ action: 'subscribe', channel }); }
	unsubscribe(channel) { return this._sendWithReply({ action: 'unsubscribe', channel }); }
	broadcast(channel, data) { return this._sendWithReply({ action: 'broadcast', channel, data }); }
	ping() { return this._sendWithReply({ action: 'ping' }); }
	api(method, path, body = null) { return this._sendWithReply({ action: 'api', data: { method, path, body } }); }
}


/** Custom error class for Moonstone API errors. */
class MoonstoneBridgeError extends Error {
	constructor(message, status, data) {
		super(message);
		this.name = 'MoonstoneBridgeError';
		this.status = status;
		this.data = data;
	}
}


// Backward-compatible alias (dev-bundle historically used MoonstoneAPI)
var MoonstoneAPI = MoonstoneBridge;

// Export for module environments
if (typeof module !== 'undefined' && module.exports) {
	module.exports = { MoonstoneBridge, MoonstoneBridgeWS, MoonstoneBridgeError, MoonstoneAPI };
}
