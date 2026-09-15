(function(global){
  'use strict';
  const tg = global.Telegram && global.Telegram.WebApp;
  const available = !!(tg && tg.initData !== undefined);
  const API = {
    isTelegram: available,
    user: null,
    theme: { bg: '#F5F7FB', text: '#0B2A5B', hint: '#7C8AA0', button: '#0B2A5B', buttonText: '#FFFFFF', secondary: '#F1F5F9' },
    init() {
      if (!available) return this;
      try {
        tg.ready();
        tg.expand();
        tg.disableVerticalSwipes && tg.disableVerticalSwipes();
        tg.setHeaderColor && tg.setHeaderColor('secondary_bg_color');
        tg.setBackgroundColor && tg.setBackgroundColor('#F5F7FB');
        tg.enableClosingConfirmation && tg.enableClosingConfirmation();
        const u = tg.initDataUnsafe && tg.initDataUnsafe.user;
        if (u) {
          this.user = {
            id: u.id,
            first: u.first_name || '',
            last: u.last_name || '',
            name: (u.first_name || '') + (u.last_name ? ' ' + u.last_name : '') || 'Foydalanuvchi',
            username: u.username || null,
            photo: u.photo_url || null,
            lang: u.language_code || 'uz'
          };
        }
      } catch (e) {}
      return this;
    },
    tap() { available && tg.HapticFeedback && tg.HapticFeedback.impactOccurred('light'); },
    impact() { available && tg.HapticFeedback && tg.HapticFeedback.impactOccurred('medium'); },
    success() { available && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred('success'); },
    warning() { available && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred('warning'); },
    showAlert(m) { available ? tg.showAlert(m) : alert(m); },
    showConfirm(m, cb) { available ? tg.showConfirm(m, cb) : cb(confirm(m)); }
  };
  global.WT = API;
})(window);
