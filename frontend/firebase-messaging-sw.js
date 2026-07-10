// firebase-messaging-sw.js
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-messaging-compat.js');

// These placeholders will be dynamically replaced by the backend server on startup with variables from .env
const firebaseConfig = {
    apiKey: "mock-firebase-api-key",
    authDomain: "stadiumops-ai.firebaseapp.com",
    projectId: "stadiumops-ai",
    storageBucket: "stadiumops-ai.appspot.com",
    messagingSenderId: "63483696880",
    appId: "1:63483696880:web:63483696880abcdef"
};

firebase.initializeApp(firebaseConfig);
const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
    console.log('[firebase-messaging-sw.js] Received background message ', payload);
    const notificationTitle = payload.notification.title || "StadiumOps Alert";
    const notificationOptions = {
        body: payload.notification.body || "",
        icon: "/favicon.ico"
    };

    self.registration.showNotification(notificationTitle, notificationOptions);
});
