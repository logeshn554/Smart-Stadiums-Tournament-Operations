// firebase-messaging-sw.js
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-messaging-compat.js');

const CONFIG_ENDPOINT = '/api/fcm/config';

function setupMessaging(firebaseConfig) {
    if (!firebaseConfig.apiKey || !firebaseConfig.messagingSenderId) {
        console.log('[firebase-messaging-sw.js] Firebase config unavailable. Background alerts disabled.');
        return;
    }

    if (!firebase.apps.length) {
        firebase.initializeApp(firebaseConfig);
    }

    const messaging = firebase.messaging();

    messaging.onBackgroundMessage((payload) => {
        console.log('[firebase-messaging-sw.js] Received background message ', payload);
        const notificationTitle = payload.notification.title || 'StadiumOps Alert';
        const notificationOptions = {
            body: payload.notification.body || '',
            icon: '/favicon.ico'
        };

        self.registration.showNotification(notificationTitle, notificationOptions);
    });
}

fetch(CONFIG_ENDPOINT, { cache: 'no-store' })
    .then((response) => {
        if (!response.ok) {
            throw new Error('Unable to load Firebase config');
        }
        return response.json();
    })
    .then((firebaseConfig) => setupMessaging(firebaseConfig))
    .catch((error) => {
        console.log('[firebase-messaging-sw.js] FCM initialization skipped:', error);
    });
