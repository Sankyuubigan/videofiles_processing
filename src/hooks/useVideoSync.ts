import { useEffect } from 'react';

export function useVideoSync(
  leaderRef: React.RefObject<HTMLVideoElement | null>,
  followerRef: React.RefObject<HTMLVideoElement | null>,
  tolerance: number = 0.05
) {
  useEffect(() => {
    let animFrameId: number;

    const syncLoop = () => {
      const leader = leaderRef.current;
      const follower = followerRef.current;

      if (leader && follower) {
        // Синхронизируем состояние воспроизведения
        if (!leader.paused && follower.paused) {
          follower.play().catch(() => {});
        } else if (leader.paused && !follower.paused) {
          follower.pause();
        }

        // Синхронизируем скорость воспроизведения
        if (follower.playbackRate !== leader.playbackRate) {
          follower.playbackRate = leader.playbackRate;
        }

        // Синхронизируем время (рассинхрон)
        if (!leader.paused) {
          const drift = Math.abs(leader.currentTime - follower.currentTime);
          if (drift > tolerance) {
            follower.currentTime = leader.currentTime;
          }
        }
      }

      animFrameId = requestAnimationFrame(syncLoop);
    };

    animFrameId = requestAnimationFrame(syncLoop);

    return () => {
      cancelAnimationFrame(animFrameId);
    };
  }, [leaderRef, followerRef, tolerance]);
}