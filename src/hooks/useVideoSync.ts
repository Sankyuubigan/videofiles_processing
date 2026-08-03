import { useEffect } from 'react';

export function useVideoSync(
  leaderRef: React.RefObject<HTMLVideoElement | null>,
  followerRef: React.RefObject<HTMLVideoElement | null>,
  tolerance: number = 0.5
) {
  useEffect(() => {
    let animFrameId: number;
    let pendingPlay = false;
    let attachedLeader: HTMLVideoElement | null = null;

    const syncLoop = () => {
      const leader = leaderRef.current;
      const follower = followerRef.current;

      if (leader && follower) {
        // Синхронизируем состояние воспроизведения
        if (!leader.paused && follower.paused) {
          // Запускаем follower только когда у него есть данные для декода,
          // иначе play() будет отклоняться каждый кадр
          if (!pendingPlay && !follower.seeking && follower.readyState >= 2) {
            pendingPlay = true;
            follower.play()
              .catch(() => {})
              .finally(() => {
                pendingPlay = false;
              });
          }
        } else if (leader.paused && !follower.paused) {
          follower.pause();
        }

        // Синхронизируем скорость воспроизведения
        if (follower.playbackRate !== leader.playbackRate) {
          follower.playbackRate = leader.playbackRate;
        }

        // Синхронизируем время. Не трогаем follower, пока он буферизует
        // (seeking / нет данных), иначе постоянный seek не даёт ему докачать
        // и видео вечно зависает. Плюс порог 0.5с вместо 50мс.
        if (!leader.paused && !follower.seeking && follower.readyState >= 3) {
          const drift = Math.abs(leader.currentTime - follower.currentTime);
          if (drift > tolerance) {
            follower.currentTime = leader.currentTime;
          }
        }
      }

      // Подписываемся на play лидера, чтобы перезапустить цикл после паузы
      const leaderEl = leaderRef.current;
      if (leaderEl && leaderEl !== attachedLeader) {
        if (attachedLeader) attachedLeader.removeEventListener('play', startLoop);
        leaderEl.addEventListener('play', startLoop);
        attachedLeader = leaderEl;
      }

      // Оба на паузе - цикл не нужен, запустится заново по событию play
      if (leader && follower && leader.paused && follower.paused) {
        return;
      }

      animFrameId = requestAnimationFrame(syncLoop);
    };

    const startLoop = () => {
      cancelAnimationFrame(animFrameId);
      animFrameId = requestAnimationFrame(syncLoop);
    };

    animFrameId = requestAnimationFrame(syncLoop);

    return () => {
      cancelAnimationFrame(animFrameId);
      if (attachedLeader) attachedLeader.removeEventListener('play', startLoop);
    };
  }, [leaderRef, followerRef, tolerance]);
}
