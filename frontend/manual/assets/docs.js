/* Local-only navigation, search and copy. No fetches, analytics or storage. */
(() => {
  'use strict';

  function init() {
    const root = document.documentElement;
    const sidebar = document.getElementById('docs-sidebar');
    const main = document.getElementById('main-content');
    const search = document.getElementById('doc-search');
    const menuToggle = document.getElementById('menu-toggle');
    const header = document.querySelector('.topbar');
    const sections = Array.from(document.querySelectorAll('section.doc-section[id]'));
    const navLinks = sidebar ? Array.from(sidebar.querySelectorAll('nav a[href^="#"]')) : [];
    const narrowScreen = window.matchMedia('(max-width: 800px)');
    const copyTimers = new WeakMap();
    const originalCopyContents = new WeakMap();
    const originalDetailsState = new Map();
    let searchTimer;
    let scrollFrame = 0;
    let currentQuery = '';
    let searchStatus = document.getElementById('search-status');

    if (!main || !sections.length) return;
    root.classList.add('js');

    if (!document.querySelector('.skip-link')) {
      const skip = document.createElement('a');
      skip.className = 'skip-link';
      skip.href = '#main-content';
      skip.textContent = '跳到正文';
      document.body.prepend(skip);
    }
    if (!main.hasAttribute('tabindex')) main.tabIndex = -1;
    if (sidebar && !sidebar.hasAttribute('aria-label')) sidebar.setAttribute('aria-label', '文档目录');

    function targetId(link) {
      try { return decodeURIComponent(link.hash.slice(1)); }
      catch { return link.hash.slice(1); }
    }

    const index = sections.map(section => ({
      section,
      title: section.dataset.title || section.querySelector('h1, h2, h3')?.textContent || section.id,
      text: `${section.dataset.title || ''} ${section.textContent || ''}`.replace(/\s+/g, ' ').toLocaleLowerCase(),
      links: navLinks.filter(link => targetId(link) === section.id),
    }));

    // Keep the offset accurate if the header wraps or the reader increases text size.
    function updateHeaderHeight() {
      if (!header) return;
      const height = `${Math.ceil(header.getBoundingClientRect().height)}px`;
      if (root.style.getPropertyValue('--header-height') !== height) root.style.setProperty('--header-height', height);
    }
    updateHeaderHeight();
    if ('ResizeObserver' in window && header) new ResizeObserver(updateHeaderHeight).observe(header);

    const backdrop = document.createElement('div');
    backdrop.className = 'nav-backdrop';
    backdrop.hidden = true;
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.append(backdrop);

    function setMenu(open, returnFocus = false) {
      if (!sidebar || !menuToggle) return;
      const expanded = Boolean(open && narrowScreen.matches);
      document.body.classList.toggle('nav-open', expanded);
      menuToggle.setAttribute('aria-expanded', String(expanded));
      menuToggle.setAttribute('aria-label', expanded ? '关闭文档目录' : '打开文档目录');
      backdrop.hidden = !expanded;
      if (expanded) {
        const firstLink = navLinks.find(link => !link.hidden);
        // An empty search result leaves the close control as the only tab stop.
        (firstLink || menuToggle).focus({ preventScroll: true });
      } else if (returnFocus) {
        menuToggle.focus({ preventScroll: true });
      }
    }

    if (menuToggle && sidebar) {
      menuToggle.type = 'button';
      menuToggle.setAttribute('aria-controls', 'docs-sidebar');
      menuToggle.setAttribute('aria-expanded', 'false');
      menuToggle.setAttribute('aria-label', '打开文档目录');
      sidebar.tabIndex = -1;
      menuToggle.addEventListener('click', () => setMenu(!document.body.classList.contains('nav-open')));
      backdrop.addEventListener('click', () => setMenu(false, true));
    }

    function updateActiveSection() {
      scrollFrame = 0;
      const visibleSections = sections.filter(section => !section.hidden);
      const threshold = (header?.getBoundingClientRect().bottom || 0) + 64;
      let activeSection = visibleSections[0];
      for (const section of visibleSections) {
        if (section.getBoundingClientRect().top <= threshold) activeSection = section;
        else break;
      }
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 5) {
        activeSection = visibleSections[visibleSections.length - 1];
      }
      for (const link of navLinks) {
        // The open route is already marked by its colour; highlighting it too made it the loudest item.
        const active = !link.hidden && !link.classList.contains('nav-route') && targetId(link) === activeSection?.id;
        link.classList.toggle('active', active);
        if (active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
    }

    function queueActiveUpdate() {
      if (!scrollFrame) scrollFrame = window.requestAnimationFrame(updateActiveSection);
    }
    window.addEventListener('scroll', queueActiveUpdate, { passive: true });
    window.addEventListener('resize', () => { updateHeaderHeight(); queueActiveUpdate(); }, { passive: true });
    window.addEventListener('load', queueActiveUpdate, { once: true });
    const handleScreenChange = () => { setMenu(false); queueActiveUpdate(); };
    if (narrowScreen.addEventListener) narrowScreen.addEventListener('change', handleScreenChange);
    else narrowScreen.addListener(handleScreenChange);

    for (const link of navLinks) {
      link.addEventListener('click', () => {
        setMenu(false);
        const target = document.getElementById(targetId(link));
        if (target) {
          if (!target.hasAttribute('tabindex')) target.tabIndex = -1;
          target.focus({ preventScroll: true });
        }
        queueActiveUpdate();
      });
    }

    function removeHighlights() {
      for (const section of sections) {
        const parents = new Set();
        section.querySelectorAll('mark.search-highlight').forEach(mark => {
          const parent = mark.parentNode;
          if (!parent) return;
          parents.add(parent);
          mark.replaceWith(document.createTextNode(mark.textContent || ''));
        });
        parents.forEach(parent => parent.normalize());
      }
    }

    function escapeRegex(value) {
      return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function highlightSection(section, terms) {
      const pattern = new RegExp(terms.slice().sort((a, b) => b.length - a.length).map(escapeRegex).join('|'), 'giu');
      const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          if (!node.textContent.trim() || node.parentElement?.closest('script, style, button, textarea, input, select, [aria-hidden="true"], mark')) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      const textNodes = [];
      while (walker.nextNode()) textNodes.push(walker.currentNode);
      for (const node of textNodes) {
        const content = node.textContent;
        pattern.lastIndex = 0;
        let match = pattern.exec(content);
        if (!match) continue;
        const fragment = document.createDocumentFragment();
        let position = 0;
        while (match) {
          fragment.append(document.createTextNode(content.slice(position, match.index)));
          const mark = document.createElement('mark');
          mark.className = 'search-highlight';
          mark.textContent = match[0];
          fragment.append(mark);
          position = match.index + match[0].length;
          match = pattern.exec(content);
        }
        fragment.append(document.createTextNode(content.slice(position)));
        node.replaceWith(fragment);
      }
    }

    function clearSearch(focusInput = true) {
      if (search) search.value = '';
      applySearch('');
      if (focusInput && search) search.focus({ preventScroll: true });
    }

    function applySearch(value) {
      window.clearTimeout(searchTimer);
      const query = value.trim().slice(0, 120);
      const terms = Array.from(new Set(query.toLocaleLowerCase().split(/\s+/).filter(Boolean))).slice(0, 10);
      if (query && !currentQuery) {
        main.querySelectorAll('details').forEach(details => originalDetailsState.set(details, details.open));
      }
      currentQuery = query;
      removeHighlights();
      let count = 0;
      for (const entry of index) {
        const matches = !terms.length || terms.every(term => entry.text.includes(term));
        entry.section.hidden = !matches;
        entry.links.forEach(link => { link.hidden = !matches; });
        if (matches) {
          count += 1;
          if (terms.length) highlightSection(entry.section, terms);
          entry.section.querySelectorAll('details').forEach(details => {
            if (terms.length && terms.some(term => details.textContent.toLocaleLowerCase().includes(term))) details.open = true;
          });
        }
      }
      if (!query) {
        originalDetailsState.forEach((open, details) => { details.open = open; });
        originalDetailsState.clear();
      }
      if (searchStatus) {
        searchStatus.hidden = !query;
        searchStatus.replaceChildren();
        searchStatus.removeAttribute('data-no-results');
        if (query) {
          const message = document.createElement('span');
          message.textContent = count ? `找到 ${count} 个相关章节（共 ${sections.length} 个）` : '没有找到相关章节。试试“注册”“密钥”或“额度”。';
          const clearButton = document.createElement('button');
          clearButton.type = 'button';
          clearButton.className = 'search-clear';
          clearButton.textContent = '清除搜索';
          clearButton.addEventListener('click', () => clearSearch());
          searchStatus.append(message, clearButton);
          if (!count) searchStatus.dataset.noResults = 'true';
          // Keep the result feedback visible when a search starts halfway down the page.
          if (document.activeElement === search) searchStatus.scrollIntoView({ block: 'nearest', behavior: 'auto' });
        }
      }
      queueActiveUpdate();
    }

    if (search) {
      search.type = 'search';
      search.maxLength = 120;
      search.autocomplete = 'off';
      search.spellcheck = false;
      if (!search.hasAttribute('aria-label')) search.setAttribute('aria-label', '搜索本页文档');
      if (!searchStatus) {
        searchStatus = document.createElement('div');
        searchStatus.id = 'search-status';
        main.prepend(searchStatus);
      }
      searchStatus.classList.add('search-status');
      searchStatus.setAttribute('role', 'status');
      searchStatus.setAttribute('aria-live', 'polite');
      searchStatus.setAttribute('aria-atomic', 'true');
      search.setAttribute('aria-controls', 'main-content');
      search.addEventListener('compositionstart', () => window.clearTimeout(searchTimer));
      search.addEventListener('input', event => {
        // Only the reader typing filters the page. Browser autofill writes into unfocused fields
        // (for example a saved login email) and must never hide every section.
        if (document.activeElement !== search) {
          if (!currentQuery) search.value = '';
          return;
        }
        if (event.isComposing) return;
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => applySearch(search.value), 140);
      });
      search.addEventListener('compositionend', () => applySearch(search.value));
      search.addEventListener('search', () => applySearch(search.value));
      search.addEventListener('keydown', event => {
        if (event.isComposing) return;
        if (event.key === 'Escape' && search.value) {
          event.preventDefault();
          clearSearch();
        }
        if (event.key === 'Enter') {
          event.preventDefault();
          applySearch(search.value);
          searchStatus.scrollIntoView({ block: 'nearest', behavior: 'auto' });
        }
      });
      // Drop any value the browser restored on back/forward navigation; searches are never persisted.
      search.value = '';
    }

    // A shared live region announces copies without changing the page position.
    const copyStatus = document.createElement('div');
    copyStatus.className = 'sr-only';
    copyStatus.setAttribute('role', 'status');
    copyStatus.setAttribute('aria-live', 'polite');
    document.body.append(copyStatus);

    async function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(text); return true; }
        catch { /* Continue to the local-file / older-browser fallback. */ }
      }
      const previousFocus = document.activeElement;
      const selection = window.getSelection();
      const ranges = [];
      if (selection) for (let i = 0; i < selection.rangeCount; i += 1) ranges.push(selection.getRangeAt(i).cloneRange());
      const textarea = document.createElement('textarea');
      textarea.className = 'sr-only';
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      document.body.append(textarea);
      textarea.focus({ preventScroll: true });
      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);
      let success = false;
      try { success = document.execCommand('copy'); }
      catch { success = false; }
      textarea.remove();
      if (selection) {
        selection.removeAllRanges();
        ranges.forEach(range => selection.addRange(range));
      }
      if (previousFocus instanceof HTMLElement) previousFocus.focus({ preventScroll: true });
      return success;
    }

    document.querySelectorAll('.copy-button').forEach(button => {
      if (button instanceof HTMLButtonElement) button.type = 'button';
      if (!button.hasAttribute('aria-label')) button.setAttribute('aria-label', '复制旁边的内容');
    });

    document.addEventListener('click', async event => {
      if (!(event.target instanceof Element)) return;
      const internalLink = event.target.closest('a[href^="#"]');
      if (internalLink && currentQuery) {
        const section = document.getElementById(targetId(internalLink))?.closest('.doc-section');
        if (section?.hidden) clearSearch(false);
      }
      const button = event.target.closest('.copy-button');
      if (!button || button.disabled) return;
      const value = button.closest('.copy-row')?.querySelector('.copy-value');
      const text = button.hasAttribute('data-copy') ? button.dataset.copy : (value?.value ?? value?.textContent ?? '').trim();
      if (!text) return;
      event.preventDefault();
      if (!originalCopyContents.has(button)) originalCopyContents.set(button, Array.from(button.childNodes).map(node => node.cloneNode(true)));
      window.clearTimeout(copyTimers.get(button));
      button.disabled = true;
      copyStatus.textContent = '';
      const success = await copyText(text);
      button.disabled = false;
      button.dataset.copyState = success ? 'success' : 'error';
      button.textContent = success ? '已复制' : '请手动复制';
      copyStatus.textContent = success ? '内容已复制，可以粘贴使用。' : '浏览器未能自动复制，请选中旁边的内容并手动复制。';
      copyTimers.set(button, window.setTimeout(() => {
        button.replaceChildren(...originalCopyContents.get(button).map(node => node.cloneNode(true)));
        button.removeAttribute('data-copy-state');
      }, success ? 1800 : 4500));
    });

    document.addEventListener('keydown', event => {
      if (event.isComposing) return;
      if (event.key === 'Escape' && document.body.classList.contains('nav-open')) {
        event.preventDefault();
        setMenu(false, true);
      }
      if (event.key === 'Tab' && document.body.classList.contains('nav-open') && sidebar && menuToggle) {
        const focusable = [menuToggle, ...sidebar.querySelectorAll('a[href], button, [tabindex="0"]')].filter(element => !element.hidden && element.getClientRects().length);
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!focusable.includes(document.activeElement)) {
          event.preventDefault();
          (event.shiftKey ? last : first)?.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k' && search) {
        event.preventDefault();
        setMenu(false);
        search.focus();
        search.select();
      }
    });

    window.addEventListener('hashchange', () => {
      let id;
      try { id = decodeURIComponent(window.location.hash.slice(1)); }
      catch { return; }
      const target = document.getElementById(id);
      if (target?.closest('.doc-section')?.hidden && currentQuery) {
        clearSearch(false);
        target.scrollIntoView({ block: 'start', behavior: 'auto' });
      }
      queueActiveUpdate();
    });

    const printDetailsState = new Map();
    window.addEventListener('beforeprint', () => {
      main.querySelectorAll('details').forEach(details => {
        printDetailsState.set(details, details.open);
        details.open = true;
      });
    });
    window.addEventListener('afterprint', () => {
      printDetailsState.forEach((open, details) => { details.open = open; });
      printDetailsState.clear();
    });

    updateActiveSection();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
