console.log("[*] DeepFake Agent: Мониторинг переведен на динамический режим...");

// Функция извлечения ссылки (Способ с поиском ID в цифровом следе карточки)
function getRealTikTokUrl(videoElement) {
    let current = videoElement;
    for (let i = 0; i < 7; i++) {
        if (!current) break;
        
        const htmlContent = current.outerHTML;
        const idMatch = htmlContent.match(/\b\d{18,20}\b/);
        
        if (idMatch) {
            const videoId = idMatch[0];
            return `https://www.tiktok.com/video/${videoId}`;
        }
        current = current.parentElement;
    }
    
    if (window.location.href.includes('/video/')) {
        return window.location.href;
    }
    return null;
}

// Обработчик включения видео
function handleVideoPlay(event) {
    const videoElement = event.target;
    const currentBlobUrl = videoElement.src; // Текущий blob-адрес видео в памяти

    // Если этот конкретный ролик уже анализировался — пропускаем
    if (videoElement.dataset.lastAnalyzedBlob === currentBlobUrl) {
        return;
    }

    console.log("[*] ИИ-Агент: Зафиксировано воспроизведение нового контента...");
    const realVideoUrl = getRealTikTokUrl(videoElement);
    
    if (realVideoUrl) {
        // Запоминаем текущий blob, чтобы не слать дубликаты при паузе/старте
        videoElement.dataset.lastAnalyzedBlob = currentBlobUrl;
        
        // Индикация начала анализа (желтый бордюр)
        videoElement.style.border = "4px solid yellow"; 
        console.log("[!] Отправляю на Python-сервер ссылку:", realVideoUrl);
        
        fetch("http://127.0.0.1:8000/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: realVideoUrl })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === "success") {
                if (data.is_fake) {
                    videoElement.style.border = "6px solid red";
                    console.log(`[!!!] ВЕРДИКТ ИИ: ФЕЙК (Вероятность: ${data.probability})`);
                } else {
                    videoElement.style.border = "6px solid green";
                    console.log(`[V] ВЕРДИКТ ИИ: ОРИГИНАЛ (Вероятность: ${data.probability})`);
                }
            } else {
                videoElement.style.border = "4px solid gray";
                console.error("[-] Ошибка на бэкенде:", data.message);
            }
        })
        .catch(err => {
            videoElement.style.border = "4px solid orange";
            console.error("[-] Ошибка сети с FastAPI:", err);
        });
    }
}

// Поиск плееров на странице и привязка к их событиям
function observeVideos() {
    const videos = document.querySelectorAll('video');
    videos.forEach(video => {
        if (!video.dataset.agentObserved) {
            // Слушаем событие 'play' — оно срабатывает всегда, когда включается видео (даже при скролле)
            video.addEventListener('play', handleVideoPlay);
            video.dataset.agentObserved = "true";
            console.log("[+] Взят под наблюдение динамический плеер");
        }
    });
}

// Сканируем DOM на предмет появления переиспользуемых плееров каждые 1.5 секунды
setInterval(observeVideos, 1500);