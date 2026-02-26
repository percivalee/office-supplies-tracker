(function (global) {
    const { createApp } = Vue;

    createApp({
        ...global.AppState,
        ...global.AppApi,
    }).mount('#app');

    document.getElementById('app').style.display = '';
})(window);
