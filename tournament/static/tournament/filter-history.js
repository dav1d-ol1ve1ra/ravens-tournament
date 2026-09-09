(() => {
  'use strict';

  document.addEventListener('click', (event) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      !(event.target instanceof Element)
    ) {
      return;
    }

    const link = event.target.closest('[data-replace-history-links] a[href]');
    if (!link || link.target || link.hasAttribute('download')) {
      return;
    }

    const currentUrl = new URL(window.location.href);
    const destinationUrl = new URL(link.href, currentUrl);
    if (
      destinationUrl.origin !== currentUrl.origin ||
      destinationUrl.pathname !== currentUrl.pathname
    ) {
      return;
    }

    event.preventDefault();
    window.location.replace(destinationUrl.href);
  });
})();
