/**
 * TorPay Payment Widget
 * Professional cryptocurrency payment modal inspired by BTCPay Server
 * https://torpay.me
 */

(function() {
  'use strict';

  var TorPay = {
    config: {
      apiKey: null,
      baseUrl: '',
      pollInterval: 5000,
      theme: 'dark'
    },

    cryptoInfo: {
      'BTC': {
        name: 'Bitcoin',
        color: '#f7931a',
        scheme: 'bitcoin',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#F7931A"/><path fill="#FFF" fill-rule="nonzero" d="M23.189 14.02c.314-2.096-1.283-3.223-3.465-3.975l.708-2.84-1.728-.43-.69 2.765c-.454-.114-.92-.22-1.385-.326l.695-2.783L15.596 6l-.708 2.839c-.376-.086-.746-.17-1.104-.26l.002-.009-2.384-.595-.46 1.846s1.283.294 1.256.312c.7.175.826.638.805 1.006l-.806 3.235c.048.012.11.03.18.057l-.183-.045-1.13 4.532c-.086.212-.303.531-.793.41.018.025-1.256-.314-1.256-.314l-.858 1.978 2.25.561c.418.105.828.215 1.231.318l-.715 2.872 1.727.43.708-2.84c.472.127.93.245 1.378.357l-.706 2.828 1.728.43.715-2.866c2.948.558 5.164.333 6.097-2.333.752-2.146-.037-3.385-1.588-4.192 1.13-.26 1.98-1.003 2.207-2.538zm-3.95 5.538c-.533 2.147-4.148.986-5.32.695l.95-3.805c1.172.293 4.929.872 4.37 3.11zm.535-5.569c-.487 1.953-3.495.96-4.47.717l.86-3.45c.975.243 4.118.696 3.61 2.733z"/></g></svg>'
      },
      'LTC': {
        name: 'Litecoin',
        color: '#345d9d',
        scheme: 'litecoin',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#345D9D"/><path fill="#FFF" d="M10.427 19.214L9 19.768l.688-2.759 1.444-.58L13.213 8h5.129l-1.519 6.196 1.41-.571-.68 2.75-1.427.57-.848 3.483H23L22.127 24H9.252z"/></g></svg>'
      },
      'ETH': {
        name: 'Ethereum',
        color: '#627eea',
        scheme: 'ethereum',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#627EEA"/><g fill="#FFF" fill-rule="nonzero"><path fill-opacity=".602" d="M16.498 4v8.87l7.497 3.35z"/><path d="M16.498 4L9 16.22l7.498-3.35z"/><path fill-opacity=".602" d="M16.498 21.968v6.027L24 17.616z"/><path d="M16.498 27.995v-6.028L9 17.616z"/><path fill-opacity=".2" d="M16.498 20.573l7.497-4.353-7.497-3.348z"/><path fill-opacity=".602" d="M9 16.22l7.498 4.353v-7.701z"/></g></g></svg>'
      },
      'XMR': {
        name: 'Monero',
        color: '#ff6600',
        scheme: 'monero',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#FF6600"/><path fill="#FFF" d="M15.97 5.235l5.903 5.88v8.36h2.353v-6.673L15.97 4.5 7.774 12.8v6.675h2.353v-8.36z"/><path fill="#FFF" d="M10.127 19.476h3.768v3.291H7.774v-5.88l2.353 2.353v.236zm11.843 0v-.236l2.353-2.353v5.88h-6.121v-3.291h3.768z"/></g></svg>'
      },
      'USDT-TRC20': {
        name: 'Tether TRC20',
        color: '#26a17b',
        scheme: 'tether',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#26A17B"/><path fill="#FFF" d="M17.922 17.383v-.002c-.11.008-.677.042-1.942.042-1.01 0-1.721-.03-1.971-.042v.003c-3.888-.171-6.79-.848-6.79-1.658 0-.809 2.902-1.486 6.79-1.66v2.644c.254.018.982.061 1.988.061 1.207 0 1.812-.05 1.925-.06v-2.643c3.88.173 6.775.85 6.775 1.658 0 .81-2.895 1.485-6.775 1.657m0-3.59v-2.366h5.414V7.819H8.595v3.608h5.414v2.365c-4.4.202-7.709 1.074-7.709 2.118 0 1.044 3.309 1.915 7.709 2.118v7.582h3.913v-7.584c4.393-.202 7.694-1.073 7.694-2.116 0-1.043-3.301-1.914-7.694-2.117"/></g></svg>'
      },
      'USDT-ERC20': {
        name: 'Tether ERC20',
        color: '#26a17b',
        scheme: 'tether',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#26A17B"/><path fill="#FFF" d="M17.922 17.383v-.002c-.11.008-.677.042-1.942.042-1.01 0-1.721-.03-1.971-.042v.003c-3.888-.171-6.79-.848-6.79-1.658 0-.809 2.902-1.486 6.79-1.66v2.644c.254.018.982.061 1.988.061 1.207 0 1.812-.05 1.925-.06v-2.643c3.88.173 6.775.85 6.775 1.658 0 .81-2.895 1.485-6.775 1.657m0-3.59v-2.366h5.414V7.819H8.595v3.608h5.414v2.365c-4.4.202-7.709 1.074-7.709 2.118 0 1.044 3.309 1.915 7.709 2.118v7.582h3.913v-7.584c4.393-.202 7.694-1.073 7.694-2.116 0-1.043-3.301-1.914-7.694-2.117"/></g></svg>'
      },
      'TRX': {
        name: 'Tron',
        color: '#eb0029',
        scheme: 'tron',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#EF0027"/><path fill="#FFF" d="M21.932 9.913L7.5 7.257l7.595 19.112 10.583-12.894-3.746-3.562zm-.232 1.17l2.208 2.099-6.038 1.093 3.83-3.192zm-5.142 2.973l-6.364-5.278 10.402 1.914-4.038 3.364zm-.453.934l-1.038 8.58L9.472 9.487l6.633 5.503zm.96.455l6.687-1.21-7.67 9.343.983-8.133z"/></g></svg>'
      },
      'DOGE': {
        name: 'Dogecoin',
        color: '#c2a633',
        scheme: 'dogecoin',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#C2A633"/><path fill="#FFF" d="M13.248 14.61h4.314v2.286h-4.314v4.818h2.721c1.077 0 1.958-.145 2.645-.436.687-.29 1.234-.678 1.64-1.164.407-.487.696-1.054.866-1.701.17-.647.256-1.331.256-2.052 0-.721-.086-1.405-.256-2.052-.17-.647-.459-1.214-.866-1.701-.406-.486-.953-.874-1.64-1.164-.687-.29-1.568-.436-2.645-.436h-2.721v4.602zm-2.533 7.104V9.893h5.303c1.341 0 2.469.188 3.384.564.916.376 1.658.878 2.227 1.508.57.629.98 1.353 1.232 2.17.252.818.378 1.67.378 2.558 0 .889-.126 1.74-.378 2.558-.252.817-.663 1.541-1.232 2.17-.57.63-1.311 1.132-2.227 1.508-.915.376-2.043.564-3.384.564h-5.303z"/></g></svg>'
      },
      'FIRO': {
        name: 'Firo',
        color: '#9b1c2e',
        scheme: 'firo',
        icon: '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><circle cx="16" cy="16" r="16" fill="#9B1C2E"/><path fill="#FFF" d="M10 8h12v3h-9v4h8v3h-8v6h-3z"/></g></svg>'
      }
    },

    init: function(options) {
      this.config.apiKey = options.apiKey || null;
      this.config.baseUrl = (options.baseUrl || '').replace(/\/$/, '');
      this.config.pollInterval = options.pollInterval || this.config.pollInterval;
      this.config.theme = (options.theme || 'dark').toLowerCase();
      this.injectStyles();
    },

    getCryptoIcon: function(crypto, size) {
      var info = this.cryptoInfo[crypto] || {};
      size = size || 32;
      if (info.icon) {
        return '<div class="torpay-crypto-icon" style="width:' + size + 'px;height:' + size + 'px;">' + info.icon + '</div>';
      }
      // Fallback to letter icon
      var color = info.color || '#6366f1';
      return '<div class="torpay-crypto-icon" style="background:' + color + ';width:' + size + 'px;height:' + size + 'px;">' + crypto.charAt(0) + '</div>';
    },

    injectStyles: function() {
      if (document.getElementById('torpay-widget-styles')) return;

      var css = `
        /* TorPay Payment Widget - BTCPay-inspired Dark Theme */
        .torpay-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.85);
          backdrop-filter: blur(4px);
          z-index: 999999;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: torpay-fade-in 0.2s ease;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }

        @keyframes torpay-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes torpay-slide-up {
          from { opacity: 0; transform: translateY(20px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        @keyframes torpay-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        @keyframes torpay-spin {
          to { transform: rotate(360deg); }
        }

        .torpay-modal {
          background: #1e2024;
          border-radius: 8px;
          width: 380px;
          max-width: 95vw;
          max-height: 95vh;
          overflow: hidden;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
          animation: torpay-slide-up 0.3s ease;
          display: flex;
          flex-direction: column;
        }

        /* Header with logo */
        .torpay-header {
          background: #1a1c1f;
          padding: 12px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid #2d3139;
        }

        .torpay-brand {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .torpay-brand-icon {
          width: 28px;
          height: 28px;
          background: linear-gradient(135deg, #51b87d 0%, #3d9a68 100%);
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .torpay-brand-icon svg {
          width: 16px;
          height: 16px;
          fill: none;
          stroke: white;
          stroke-width: 2;
        }

        .torpay-brand-name {
          font-size: 16px;
          font-weight: 600;
          color: #fff;
        }

        .torpay-close {
          width: 28px;
          height: 28px;
          border: none;
          background: transparent;
          color: #6b7280;
          cursor: pointer;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s ease;
        }

        .torpay-close:hover {
          background: #374151;
          color: #fff;
        }

        /* Status bar */
        .torpay-status-bar {
          background: #51b87d;
          padding: 8px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .torpay-status-bar.pending { background: #51b87d; }
        .torpay-status-bar.partial { background: #f59e0b; }
        .torpay-status-bar.paid { background: #10b981; }
        .torpay-status-bar.expired { background: #ef4444; }

        .torpay-status-left {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #fff;
          font-size: 13px;
          font-weight: 500;
        }

        .torpay-status-left svg {
          width: 14px;
          height: 14px;
          animation: torpay-spin 2s linear infinite;
        }

        .torpay-status-bar.paid .torpay-status-left svg,
        .torpay-status-bar.expired .torpay-status-left svg {
          animation: none;
        }

        .torpay-timer {
          color: #fff;
          font-size: 14px;
          font-weight: 700;
          font-family: 'SF Mono', Monaco, 'Courier New', monospace;
        }

        /* Crypto selector row */
        .torpay-crypto-row {
          padding: 10px 16px;
          background: #1a1c1f;
          border-bottom: 1px solid #2d3139;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .torpay-crypto-label {
          font-size: 12px;
          color: #9ca3af;
        }

        .torpay-crypto-badge {
          display: flex;
          align-items: center;
          gap: 8px;
          background: #2d3139;
          padding: 6px 12px;
          border-radius: 6px;
        }

        .torpay-crypto-icon {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 9px;
          color: #fff;
          overflow: hidden;
          flex-shrink: 0;
        }

        .torpay-crypto-icon svg {
          width: 100%;
          height: 100%;
        }

        .torpay-crypto-name {
          color: #fff;
          font-size: 13px;
          font-weight: 600;
        }

        /* Amount row */
        .torpay-amount-row {
          padding: 10px 16px;
          background: #1a1c1f;
          border-bottom: 1px solid #2d3139;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .torpay-amount-label {
          font-size: 12px;
          color: #9ca3af;
        }

        .torpay-amount-value {
          text-align: right;
        }

        .torpay-amount-crypto {
          font-size: 16px;
          font-weight: 700;
          color: #fff;
          font-family: 'SF Mono', Monaco, 'Courier New', monospace;
        }

        .torpay-amount-fiat {
          font-size: 11px;
          color: #6b7280;
          margin-top: 2px;
        }

        /* Tabs */
        .torpay-tabs {
          display: flex;
          background: #1e2024;
          border-bottom: 1px solid #2d3139;
        }

        .torpay-tab {
          flex: 1;
          padding: 12px 16px;
          background: transparent;
          border: none;
          color: #6b7280;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          position: relative;
        }

        .torpay-tab:hover { color: #9ca3af; }
        .torpay-tab.active { color: #fff; }

        .torpay-tab.active::after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 16px;
          right: 16px;
          height: 2px;
          background: #51b87d;
        }

        /* Tab content */
        .torpay-tab-content {
          display: none;
          padding: 20px 16px;
          background: #1e2024;
        }

        .torpay-tab-content.active {
          display: block;
        }

        /* QR Code section */
        .torpay-qr-section {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .torpay-qr-wrapper {
          background: #fff;
          padding: 12px;
          border-radius: 8px;
          position: relative;
        }

        .torpay-qr-wrapper canvas,
        .torpay-qr-wrapper img {
          display: block;
          width: 180px;
          height: 180px;
        }

        .torpay-qr-logo {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 44px;
          height: 44px;
          background: #fff;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        }

        .torpay-qr-logo-inner {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 12px;
          color: #fff;
          overflow: hidden;
        }

        .torpay-qr-logo-inner .torpay-crypto-icon {
          width: 100%;
          height: 100%;
          border-radius: 50%;
        }

        .torpay-wallet-btn {
          margin-top: 14px;
          width: 100%;
          padding: 12px 20px;
          background: #51b87d;
          border: none;
          border-radius: 6px;
          color: #fff;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          text-decoration: none;
        }

        .torpay-wallet-btn:hover {
          background: #45a06d;
        }

        .torpay-fee-note {
          margin-top: 10px;
          font-size: 11px;
          color: #6b7280;
        }

        /* Copy section */
        .torpay-copy-section {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .torpay-copy-field {
          background: #2d3139;
          border-radius: 6px;
          padding: 12px;
        }

        .torpay-copy-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #6b7280;
          margin-bottom: 6px;
          font-weight: 600;
        }

        .torpay-copy-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .torpay-copy-value {
          flex: 1;
          font-family: 'SF Mono', Monaco, 'Courier New', monospace;
          font-size: 12px;
          color: #fff;
          word-break: break-all;
          line-height: 1.4;
        }

        .torpay-copy-btn {
          flex-shrink: 0;
          width: 32px;
          height: 32px;
          background: #374151;
          border: none;
          border-radius: 4px;
          color: #9ca3af;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s ease;
        }

        .torpay-copy-btn:hover {
          background: #4b5563;
          color: #fff;
        }

        .torpay-copy-btn.copied {
          background: #51b87d;
          color: #fff;
        }

        /* Pay button */
        .torpay-pay-btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          padding: 14px 28px;
          background: linear-gradient(135deg, #51b87d 0%, #3d9a68 100%);
          color: #fff;
          font-size: 16px;
          font-weight: 600;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 14px rgba(81, 184, 125, 0.35);
        }

        .torpay-pay-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 6px 20px rgba(81, 184, 125, 0.45);
        }

        .torpay-pay-btn svg {
          width: 20px;
          height: 20px;
        }

        /* Success state */
        .torpay-success {
          text-align: center;
          padding: 32px 20px;
        }

        .torpay-success-icon {
          width: 64px;
          height: 64px;
          background: #10b981;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 16px;
        }

        .torpay-success-icon svg {
          width: 32px;
          height: 32px;
          stroke: #fff;
        }

        .torpay-success-title {
          font-size: 18px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 6px;
        }

        .torpay-success-text {
          font-size: 13px;
          color: #9ca3af;
        }

        /* Loading state */
        .torpay-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 50px 20px;
        }

        .torpay-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #2d3139;
          border-top-color: #51b87d;
          border-radius: 50%;
          animation: torpay-spin 0.8s linear infinite;
          margin-bottom: 14px;
        }

        .torpay-loading-text {
          color: #9ca3af;
          font-size: 13px;
        }

        /* Error state */
        .torpay-error {
          text-align: center;
          padding: 32px 20px;
        }

        .torpay-error-icon {
          width: 64px;
          height: 64px;
          background: #ef4444;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 16px;
        }

        .torpay-error-title {
          font-size: 18px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 6px;
        }

        .torpay-error-text {
          font-size: 13px;
          color: #9ca3af;
        }

        /* Currency Selector */
        .torpay-selector-body {
          padding: 20px;
        }

        .torpay-selector-amount {
          text-align: center;
          padding: 20px;
          background: #262930;
          border-radius: 8px;
          margin-bottom: 20px;
        }

        .torpay-selector-amount-label {
          font-size: 12px;
          color: #9ca3af;
          margin-bottom: 6px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .torpay-selector-amount-value {
          font-size: 28px;
          font-weight: 700;
          color: #fff;
        }

        .torpay-selector-amount-value span {
          font-size: 14px;
          font-weight: 500;
          color: #9ca3af;
        }

        .torpay-selector-title {
          font-size: 13px;
          color: #9ca3af;
          margin-bottom: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .torpay-crypto-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .torpay-crypto-option {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 16px;
          background: #262930;
          border: 1px solid #363940;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.15s ease;
          width: 100%;
          text-align: left;
          color: inherit;
          font-family: inherit;
        }

        .torpay-crypto-option:hover {
          background: #2d3139;
          border-color: #51b87d;
        }

        .torpay-crypto-option-icon {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-weight: 700;
          font-size: 16px;
          flex-shrink: 0;
        }

        .torpay-crypto-option-info {
          flex: 1;
        }

        .torpay-crypto-option-name {
          font-size: 15px;
          font-weight: 600;
          color: #fff;
          margin-bottom: 2px;
        }

        .torpay-crypto-option-symbol {
          font-size: 12px;
          color: #9ca3af;
        }

        .torpay-crypto-option-arrow {
          color: #9ca3af;
          flex-shrink: 0;
        }

        .torpay-crypto-option:hover .torpay-crypto-option-arrow {
          color: #51b87d;
        }

        /* Crypto Row Dropdown */
        .torpay-crypto-row.clickable {
          cursor: pointer;
          position: relative;
        }

        .torpay-crypto-row.clickable:hover {
          background: #262930;
        }

        .torpay-crypto-row.clickable .torpay-crypto-badge {
          cursor: pointer;
        }

        .torpay-crypto-arrow {
          margin-left: 4px;
          transition: transform 0.2s ease;
        }

        .torpay-crypto-row.open .torpay-crypto-arrow {
          transform: rotate(180deg);
        }

        .torpay-dropdown {
          position: absolute;
          top: 100%;
          left: 0;
          right: 0;
          background: #262930;
          border: 1px solid #363940;
          border-radius: 8px;
          margin-top: 4px;
          padding: 6px;
          z-index: 100;
          display: none;
          max-height: 240px;
          overflow-y: auto;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
        }

        .torpay-crypto-row.open .torpay-dropdown {
          display: block;
        }

        .torpay-dropdown-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          background: transparent;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          width: 100%;
          text-align: left;
          color: #fff;
          font-family: inherit;
          font-size: 14px;
          transition: background 0.15s ease;
        }

        .torpay-dropdown-item:hover {
          background: #363940;
        }

        .torpay-dropdown-item.selected {
          background: rgba(81, 184, 125, 0.15);
        }

        .torpay-dropdown-item .torpay-crypto-icon {
          width: 28px;
          height: 28px;
          font-size: 12px;
        }

        .torpay-dropdown-item span {
          flex: 1;
        }

        .torpay-dropdown-item svg {
          color: #51b87d;
        }

        /* Mobile responsive */
        @media (max-width: 440px) {
          .torpay-modal {
            width: 100%;
            max-width: 100%;
            max-height: 100%;
            border-radius: 0;
          }

          .torpay-qr-wrapper canvas,
          .torpay-qr-wrapper img {
            width: 160px;
            height: 160px;
          }
        }

        /* Light theme overrides */
        .torpay-theme-light .torpay-modal { background: #ffffff; color: #0f172a; box-shadow: 0 20px 50px rgba(0,0,0,0.2); }
        .torpay-theme-light .torpay-header { background: #f3f4f6; border-bottom: 1px solid #e5e7eb; }
        .torpay-theme-light .torpay-brand-name { color: #0f172a; }
        .torpay-theme-light .torpay-status-bar { background: #22c55e; color: #0f172a; }
        .torpay-theme-light .torpay-status-left { color: #0f172a; }
        .torpay-theme-light .torpay-crypto-row,
        .torpay-theme-light .torpay-amount-row { background: #f8fafc; border-bottom: 1px solid #e5e7eb; }
        .torpay-theme-light .torpay-crypto-label,
        .torpay-theme-light .torpay-amount-label,
        .torpay-theme-light .torpay-amount-fiat,
        .torpay-theme-light .torpay-tab { color: #475569; }
        .torpay-theme-light .torpay-tab.active { color: #0f172a; }
        .torpay-theme-light .torpay-tab.active::after { background: #22c55e; }
        .torpay-theme-light .torpay-tabs { border-bottom: 1px solid #e5e7eb; background: #f8fafc; }
        .torpay-theme-light .torpay-tab-content { background: #ffffff; }
        .torpay-theme-light .torpay-copy-field,
        .torpay-theme-light .torpay-crypto-badge { background: #f8fafc; border: 1px solid #e5e7eb; }
        .torpay-theme-light .torpay-copy-label { color: #475569; }
        .torpay-theme-light .torpay-copy-btn { background: #e5e7eb; color: #475569; }
        .torpay-theme-light .torpay-copy-btn:hover { background: #d4d4d8; color: #111827; }
        .torpay-theme-light .torpay-qr-wrapper { background: #f8fafc; }
        .torpay-theme-light .torpay-wallet-btn { background: #16a34a; }
        .torpay-theme-light .torpay-wallet-btn:hover { background: #15803d; }
        .torpay-theme-light .torpay-pay-btn { background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); box-shadow: 0 4px 14px rgba(16, 163, 74, 0.35); }
        .torpay-theme-light .torpay-pay-btn:hover { box-shadow: 0 6px 20px rgba(16, 163, 74, 0.45); }
        .torpay-theme-light .torpay-overlay { background: rgba(0,0,0,0.35); }
        .torpay-theme-light .torpay-crypto-name,
        .torpay-theme-light .torpay-amount-crypto,
        .torpay-theme-light .torpay-crypto-label,
        .torpay-theme-light .torpay-amount-label { color: #0f172a; }
        .torpay-theme-light .torpay-amount-fiat { color: #334155; }
        .torpay-theme-light .torpay-status-left { color: #0f172a; }
        .torpay-theme-light .torpay-status-left svg { stroke: #0f172a; }
        .torpay-theme-light .torpay-tab { color: #475569; }
        .torpay-theme-light .torpay-copy-value { color: #0f172a; }
        .torpay-theme-light .torpay-copy-row svg { stroke: #0f172a; }

        /* Emerald accent theme */
        .torpay-theme-emerald .torpay-status-bar { background: #10b981; }
        .torpay-theme-emerald .torpay-brand-icon { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
        .torpay-theme-emerald .torpay-pay-btn { background: linear-gradient(135deg, #10b981 0%, #059669 100%); box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35); }
        .torpay-theme-emerald .torpay-pay-btn:hover { box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45); }
        .torpay-theme-emerald .torpay-wallet-btn { background: #10b981; }
        .torpay-theme-emerald .torpay-wallet-btn:hover { background: #0f9f72; }
      `;

      var style = document.createElement('style');
      style.id = 'torpay-widget-styles';
      style.textContent = css;
      document.head.appendChild(style);
    },

    createButton: function(selector, options) {
      var container = typeof selector === 'string' ? document.querySelector(selector) : selector;
      if (!container) {
        console.error('TorPay: Container not found:', selector);
        return;
      }

      var self = this;
      var amount = options.amount || 0;
      var buttonText = options.buttonText || ('Pay $' + amount.toFixed(2));

      var button = document.createElement('button');
      button.className = 'torpay-pay-btn';
      button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>' + buttonText;

      button.addEventListener('click', function() {
        self.openPaymentModal(options);
      });

      container.appendChild(button);
    },

    openPaymentModal: function(options) {
      var self = this;

      var overlay = document.createElement('div');
      overlay.className = 'torpay-overlay';
      var theme = (options.theme || this.config.theme || 'dark').toLowerCase();
      overlay.classList.add('torpay-theme-' + theme);

      var modal = document.createElement('div');
      modal.className = 'torpay-modal';

      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      document.body.style.overflow = 'hidden';

      var closeModal = function() {
        overlay.remove();
        document.body.style.overflow = '';
        if (self.pollTimer) clearInterval(self.pollTimer);
        if (self.timerInterval) clearInterval(self.timerInterval);
        if (options.onClose) options.onClose();
      };

      overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeModal();
      });

      document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
          closeModal();
          document.removeEventListener('keydown', escHandler);
        }
      });

      // Store available cryptos for currency switching
      var availableCryptos = options.cryptos || (options.crypto ? [options.crypto] : ['BTC']);
      options._availableCryptos = availableCryptos;

      // Default to first crypto (BTC if available) and show payment directly
      if (!options.crypto) {
        options.crypto = availableCryptos[0];
      }

      // Go directly to payment screen
      self.proceedToPayment(modal, options, closeModal);
    },

    proceedToPayment: function(modal, options, closeModal) {
      var self = this;
      modal.innerHTML = this.renderLoading();

      // Demo mode - show mock payment without real API call
      if (options.demo) {
        var mockInvoice = self.createMockInvoice(options);
        modal.innerHTML = self.renderPaymentModal(mockInvoice, options);
        self.setupModalHandlers(modal, mockInvoice, options, closeModal);
        if (options.onSuccess) options.onSuccess(mockInvoice);
        return;
      }

      this.createPayment(options, function(error, invoice) {
        if (error) {
          modal.innerHTML = self.renderError(error);
          if (options.onError) options.onError(error);
          return;
        }

        invoice.crypto = options.crypto || 'BTC';
        modal.innerHTML = self.renderPaymentModal(invoice, options);
        self.setupModalHandlers(modal, invoice, options, closeModal);

        if (options.onSuccess) options.onSuccess(invoice);
        self.startPolling(invoice, options, modal, closeModal);
      });
    },

    renderCurrencySelector: function(options, cryptos) {
      var self = this;
      var amount = options.amount || 0;
      var currency = options.currency || 'USD';

      var cryptoItems = cryptos.map(function(crypto) {
        var info = self.cryptoInfo[crypto] || { name: crypto, color: '#6366f1' };
        return `
          <button class="torpay-crypto-option" data-crypto="${crypto}">
            <div class="torpay-crypto-option-icon" style="background:${info.color};">${crypto.charAt(0)}</div>
            <div class="torpay-crypto-option-info">
              <div class="torpay-crypto-option-name">${info.name}</div>
              <div class="torpay-crypto-option-symbol">${crypto}</div>
            </div>
            <svg class="torpay-crypto-option-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        `;
      }).join('');

      return `
        <div class="torpay-header">
          <div class="torpay-brand">
            <div class="torpay-brand-icon"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div>
            <span class="torpay-brand-name">TorPay</span>
          </div>
          <button class="torpay-close" data-action="close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="torpay-selector-body">
          <div class="torpay-selector-amount">
            <div class="torpay-selector-amount-label">Payment Amount</div>
            <div class="torpay-selector-amount-value">$${amount.toFixed(2)} <span>${currency}</span></div>
          </div>

          <div class="torpay-selector-title">Select Payment Method</div>

          <div class="torpay-crypto-list">
            ${cryptoItems}
          </div>
        </div>
      `;
    },

    setupCurrencySelectorHandlers: function(modal, options, cryptos, closeModal) {
      var self = this;

      // Close button
      var closeBtn = modal.querySelector('[data-action="close"]');
      if (closeBtn) closeBtn.addEventListener('click', closeModal);

      // Crypto selection
      modal.querySelectorAll('.torpay-crypto-option').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var selectedCrypto = this.getAttribute('data-crypto');
          options.crypto = selectedCrypto;
          self.proceedToPayment(modal, options, closeModal);
        });
      });
    },

    createMockInvoice: function(options) {
      var crypto = options.crypto || 'BTC';
      var amount = options.amount || 99.99;
      var mockAddresses = {
        'BTC': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
        'LTC': 'ltc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
        'ETH': '0x742d35Cc6634C0532925a3b844Bc9e7595f8A3B2',
        'XMR': '48VcTstRuRU9F3NM9RJJy8pXuZLYaGkKcZ3FBV9xM4r8fH7qB3CfHDz9J7gHQZ2qWDgXrLT5cZmWLbK4F8WdJuVVVQ2rXSd',
        'USDT-TRC20': 'TN2HNzHV7uNGPNmxKbLJ7cP6VyLq4yCCms',
        'USDT-ERC20': '0x742d35Cc6634C0532925a3b844Bc9e7595f8A3B2',
        'TRX': 'TN2HNzHV7uNGPNmxKbLJ7cP6VyLq4yCCms',
        'DOGE': 'DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L'
      };
      var mockRates = {
        'BTC': 0.00102,
        'LTC': 1.08,
        'ETH': 0.028,
        'XMR': 0.52,
        'USDT-TRC20': 99.99,
        'USDT-ERC20': 99.99,
        'TRX': 485.5,
        'DOGE': 248.6
      };
      return {
        id: 'demo-' + Date.now(),
        crypto: crypto,
        wallet: mockAddresses[crypto] || mockAddresses['BTC'],
        dest: mockAddresses[crypto] || mockAddresses['BTC'],
        amount: (mockRates[crypto] || 0.001) * (amount / 99.99),
        amount_crypto: (mockRates[crypto] || 0.001) * (amount / 99.99),
        amount_fiat: amount,
        fiat: options.currency || 'USD',
        exchange_rate: (99.99 / (mockRates[crypto] || 0.001)),
        status: 'PENDING',
        expires_at: Date.now() + (15 * 60 * 1000) // 15 minutes
      };
    },

    renderLoading: function() {
      return '<div class="torpay-loading"><div class="torpay-spinner"></div><div class="torpay-loading-text">Creating payment...</div></div>';
    },

    renderError: function(error) {
      return `
        <div class="torpay-header">
          <div class="torpay-brand">
            <div class="torpay-brand-icon"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div>
            <span class="torpay-brand-name">TorPay</span>
          </div>
        </div>
        <div class="torpay-error">
          <div class="torpay-error-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></div>
          <div class="torpay-error-title">Payment Error</div>
          <div class="torpay-error-text">${error}</div>
        </div>
      `;
    },

    renderPaymentModal: function(invoice, options) {
      var self = this;
      var crypto = invoice.crypto || 'BTC';
      var info = this.cryptoInfo[crypto] || { name: crypto, color: '#6366f1', scheme: crypto.toLowerCase() };
      var amount = invoice.amount || invoice.amount_crypto || '0';
      var address = invoice.wallet || invoice.dest || invoice.address || '';
      var rate = invoice.exchange_rate || '0';
      var expiresAt = invoice.expires_at ? new Date(invoice.expires_at).getTime() : (Date.now() + 15 * 60 * 1000);

      // Check if multiple cryptos available
      var availableCryptos = options._availableCryptos || [crypto];
      var hasMultipleCryptos = availableCryptos.length > 1;

      // Build dropdown items if multiple cryptos
      var dropdownItems = '';
      if (hasMultipleCryptos) {
        dropdownItems = availableCryptos.map(function(c) {
          var cInfo = self.cryptoInfo[c] || { name: c, color: '#6366f1' };
          var isSelected = c === crypto;
          return '<button class="torpay-dropdown-item' + (isSelected ? ' selected' : '') + '" data-select-crypto="' + c + '">' +
            self.getCryptoIcon(c, 20) +
            '<span>' + cInfo.name + '</span>' +
            (isSelected ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>' : '') +
          '</button>';
        }).join('');
      }

      // Get crypto icon for current selection
      var cryptoIconHtml = self.getCryptoIcon(crypto, 20);
      var qrLogoHtml = self.getCryptoIcon(crypto, 28);

      return `
        <div class="torpay-header">
          <div class="torpay-brand">
            <div class="torpay-brand-icon"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div>
            <span class="torpay-brand-name">TorPay</span>
          </div>
          <button class="torpay-close" data-action="close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="torpay-status-bar pending" data-status-bar>
          <div class="torpay-status-left">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg>
            <span data-status-text>Awaiting payment...</span>
          </div>
          <div class="torpay-timer" data-timer data-expires="${expiresAt}">--:--</div>
        </div>

        <div class="torpay-crypto-row ${hasMultipleCryptos ? 'clickable' : ''}" data-crypto-selector>
          <span class="torpay-crypto-label">Pay with</span>
          <div class="torpay-crypto-badge">
            ${cryptoIconHtml}
            <span class="torpay-crypto-name">${info.name}</span>
            ${hasMultipleCryptos ? '<svg class="torpay-crypto-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' : ''}
          </div>
          ${hasMultipleCryptos ? '<div class="torpay-dropdown" data-dropdown>' + dropdownItems + '</div>' : ''}
        </div>

        <div class="torpay-amount-row">
          <span class="torpay-amount-label">TorPay</span>
          <div class="torpay-amount-value">
            <div class="torpay-amount-crypto">${amount} ${crypto}</div>
            <div class="torpay-amount-fiat">1 ${crypto} = $${rate}</div>
          </div>
        </div>

        <div class="torpay-tabs">
          <button class="torpay-tab active" data-tab="scan">Scan</button>
          <button class="torpay-tab" data-tab="copy">Copy</button>
        </div>

        <div class="torpay-tab-content active" data-tab-content="scan">
          <div class="torpay-qr-section">
            <div class="torpay-qr-wrapper">
              <div data-qr-code></div>
              <div class="torpay-qr-logo">
                <div class="torpay-qr-logo-inner">${qrLogoHtml}</div>
              </div>
            </div>
            <a href="${info.scheme}:${address}?amount=${amount}" class="torpay-wallet-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4h-4z"/></svg>
              Open in wallet
            </a>
            <div class="torpay-fee-note">Recommended fee: sat/byte</div>
          </div>
        </div>

        <div class="torpay-tab-content" data-tab-content="copy">
          <div class="torpay-copy-section">
            <div class="torpay-copy-field">
              <div class="torpay-copy-label">Amount</div>
              <div class="torpay-copy-row">
                <div class="torpay-copy-value">${amount} ${crypto}</div>
                <button class="torpay-copy-btn" data-copy="${amount}" title="Copy amount">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                </button>
              </div>
            </div>
            <div class="torpay-copy-field">
              <div class="torpay-copy-label">Address</div>
              <div class="torpay-copy-row">
                <div class="torpay-copy-value">${address}</div>
                <button class="torpay-copy-btn" data-copy="${address}" title="Copy address">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    },

    setupModalHandlers: function(modal, invoice, options, closeModal) {
      var self = this;
      var crypto = invoice.crypto || 'BTC';
      var info = this.cryptoInfo[crypto] || { scheme: crypto.toLowerCase() };
      var address = invoice.wallet || invoice.dest || '';
      var amount = invoice.amount || invoice.amount_crypto || '0';

      // Close button
      var closeBtn = modal.querySelector('[data-action="close"]');
      if (closeBtn) closeBtn.addEventListener('click', closeModal);

      // Crypto selector dropdown
      var cryptoRow = modal.querySelector('[data-crypto-selector]');
      if (cryptoRow && cryptoRow.classList.contains('clickable')) {
        // Toggle dropdown on click
        cryptoRow.addEventListener('click', function(e) {
          // Don't toggle if clicking on a dropdown item
          if (e.target.closest('[data-select-crypto]')) return;
          cryptoRow.classList.toggle('open');
        });

        // Close dropdown when clicking outside
        modal.addEventListener('click', function(e) {
          if (!e.target.closest('[data-crypto-selector]')) {
            cryptoRow.classList.remove('open');
          }
        });

        // Handle crypto selection
        modal.querySelectorAll('[data-select-crypto]').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var selectedCrypto = this.getAttribute('data-select-crypto');
            if (selectedCrypto !== options.crypto) {
              options.crypto = selectedCrypto;
              // Clear timers before switching
              if (self.pollTimer) clearInterval(self.pollTimer);
              if (self.timerInterval) clearInterval(self.timerInterval);
              // Re-render with new crypto
              self.proceedToPayment(modal, options, closeModal);
            } else {
              cryptoRow.classList.remove('open');
            }
          });
        });
      }

      // Tab switching
      var tabs = modal.querySelectorAll('.torpay-tab');
      var contents = modal.querySelectorAll('.torpay-tab-content');
      tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
          var name = this.getAttribute('data-tab');
          tabs.forEach(function(t) { t.classList.remove('active'); });
          contents.forEach(function(c) { c.classList.remove('active'); });
          this.classList.add('active');
          modal.querySelector('[data-tab-content="' + name + '"]').classList.add('active');
        });
      });

      // Copy buttons
      modal.querySelectorAll('[data-copy]').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          var text = this.getAttribute('data-copy');
          navigator.clipboard.writeText(text).then(function() {
            btn.classList.add('copied');
            setTimeout(function() { btn.classList.remove('copied'); }, 1500);
          });
        });
      });

      // Generate QR
      var qrContainer = modal.querySelector('[data-qr-code]');
      var qrData = info.scheme + ':' + address + '?amount=' + amount;
      this.generateQR(qrContainer, qrData);

      // Start timer
      this.startTimer(modal);
    },

    generateQR: function(container, data) {
      if (typeof QRCode !== 'undefined') {
        new QRCode(container, {
          text: data,
          width: 180,
          height: 180,
          colorDark: '#000000',
          colorLight: '#ffffff',
          correctLevel: QRCode.CorrectLevel.M
        });
      } else {
        var img = document.createElement('img');
        img.src = 'https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=' + encodeURIComponent(data);
        img.alt = 'QR Code';
        img.style.cssText = 'width:180px;height:180px;';
        container.appendChild(img);
      }
    },

    startTimer: function(modal) {
      var self = this;
      var timerEl = modal.querySelector('[data-timer]');
      if (!timerEl) return;

      var expiresAt = parseInt(timerEl.getAttribute('data-expires'));
      var statusBar = modal.querySelector('[data-status-bar]');
      var statusText = modal.querySelector('[data-status-text]');

      var update = function() {
        var remaining = Math.max(0, expiresAt - Date.now());
        var min = Math.floor(remaining / 60000);
        var sec = Math.floor((remaining % 60000) / 1000);
        timerEl.textContent = min.toString().padStart(2, '0') + ':' + sec.toString().padStart(2, '0');

        if (remaining <= 0) {
          clearInterval(self.timerInterval);
          statusBar.classList.remove('pending');
          statusBar.classList.add('expired');
          statusText.textContent = 'Invoice expired';
        }
      };

      update();
      this.timerInterval = setInterval(update, 1000);
    },

    startPolling: function(invoice, options, modal, closeModal) {
      var self = this;
      var invoiceId = invoice.id;

      this.pollTimer = setInterval(function() {
        self.checkStatus(invoiceId, function(error, data) {
          if (error) return;

          var status = (data.status || '').toUpperCase();
          var statusBar = modal.querySelector('[data-status-bar]');
          var statusText = modal.querySelector('[data-status-text]');

          if (status === 'PAID' || status === 'OVERPAID') {
            clearInterval(self.pollTimer);
            clearInterval(self.timerInterval);
            statusBar.classList.remove('pending');
            statusBar.classList.add('paid');
            statusText.textContent = 'Payment confirmed!';

            setTimeout(function() {
              modal.innerHTML = self.renderSuccess();
              if (options.onPaymentComplete) options.onPaymentComplete(data);
              setTimeout(closeModal, 2500);
            }, 800);
          } else if (status === 'PARTIAL') {
            statusBar.classList.remove('pending');
            statusBar.classList.add('partial');
            statusText.textContent = 'Partial payment received';
          }
        });
      }, this.config.pollInterval);
    },

    renderSuccess: function() {
      return `
        <div class="torpay-header">
          <div class="torpay-brand">
            <div class="torpay-brand-icon"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div>
            <span class="torpay-brand-name">TorPay</span>
          </div>
        </div>
        <div class="torpay-status-bar paid">
          <div class="torpay-status-left">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            <span>Payment complete</span>
          </div>
        </div>
        <div class="torpay-success">
          <div class="torpay-success-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></div>
          <div class="torpay-success-title">Payment Received!</div>
          <div class="torpay-success-text">Your payment has been confirmed.</div>
        </div>
      `;
    },

    createPayment: function(options, callback) {
      var crypto = options.crypto || 'BTC';
      var url = this.config.baseUrl + '/api/v1/' + crypto + '/payment_request';

      var payload = {
        external_id: options.orderId || 'order-' + Date.now(),
        fiat: options.currency || 'USD',
        amount: options.amount
      };

      if (options.callbackUrl) payload.callback_url = options.callbackUrl;

      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-Torpay-Api-Key', this.config.apiKey);

      xhr.onreadystatechange = function() {
        if (xhr.readyState !== 4) return;
        try {
          var response = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300 && response.status !== 'error') {
            callback(null, response);
          } else {
            callback(response.message || response.msg || 'Payment creation failed');
          }
        } catch (e) {
          callback('Network error');
        }
      };

      xhr.send(JSON.stringify(payload));
    },

    checkStatus: function(invoiceId, callback) {
      var url = this.config.baseUrl + '/api/v1/invoice/' + invoiceId + '/status';

      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, true);
      xhr.setRequestHeader('X-Torpay-Api-Key', this.config.apiKey);

      xhr.onreadystatechange = function() {
        if (xhr.readyState !== 4) return;
        try {
          var response = JSON.parse(xhr.responseText);
          callback(xhr.status >= 200 && xhr.status < 300 ? null : 'Status check failed', response);
        } catch (e) {
          callback('Network error');
        }
      };

      xhr.send();
    }
  };

  window.TorPay = TorPay;
  window.SHKeeper = TorPay;

})();
