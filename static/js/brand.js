(function () {
  'use strict';

  // Keep internal Hermes identifiers compatible while presenting the new product name.
  const replacements = [
    ['龙虾纯对话版', '小金纯对话版'],
    ['类龙虾', '高级'],
    ['龙虾', '小金'],
    ['Hermes', '小金智能体'],
    ['HERMES', '小金智能体'],
    ['🦞', '']
  ];
  const textAttributes = ['title', 'aria-label', 'placeholder', 'alt'];

  function replaceBrand(value) {
    let result = String(value == null ? '' : value);
    replacements.forEach(([from, to]) => {
      result = result.split(from).join(to);
    });
    return result;
  }

  function rewrite(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let current;
    while ((current = walker.nextNode())) textNodes.push(current);
    textNodes.forEach((node) => {
      const parent = node.parentElement;
      if (!parent || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/i.test(parent.tagName)) return;
      const next = replaceBrand(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });
    if (root.nodeType === Node.ELEMENT_NODE) {
      textAttributes.forEach((attribute) => {
        if (!root.hasAttribute(attribute)) return;
        const next = replaceBrand(root.getAttribute(attribute));
        if (next !== root.getAttribute(attribute)) root.setAttribute(attribute, next);
      });
      root.querySelectorAll('*').forEach((element) => {
        textAttributes.forEach((attribute) => {
          if (!element.hasAttribute(attribute)) return;
          const next = replaceBrand(element.getAttribute(attribute));
          if (next !== element.getAttribute(attribute)) element.setAttribute(attribute, next);
        });
      });
    }
  }

  function boot() {
    rewrite(document.documentElement);
    document.title = replaceBrand(document.title);
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'characterData') {
          const next = replaceBrand(mutation.target.nodeValue);
          if (next !== mutation.target.nodeValue) mutation.target.nodeValue = next;
        }
        if (mutation.type === 'attributes') rewrite(mutation.target);
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) {
            const next = replaceBrand(node.nodeValue);
            if (next !== node.nodeValue) node.nodeValue = next;
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            rewrite(node);
          }
        });
      });
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: textAttributes
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
