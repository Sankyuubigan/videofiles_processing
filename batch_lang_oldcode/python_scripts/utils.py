from progress_ffmpeg import ProgressFfmpeg
import ffmpeg


def run_with_pb(input_path,ffmpeg_out):
    with ProgressFfmpeg(float(ffmpeg.probe(input_path)['format']['duration'])) as progress:
        ffmpeg.run(ffmpeg_out.global_args('-progress', progress.output_file.name), capture_stdout=True, capture_stderr=True)


def remove_silence(input_file, output_file, silence_threshold=0.005, min_duration=0.5):
    """
    Удаляет тишину из видео на основе амплитуды аудиодорожки.

    :param input_file: Путь к входному видеофайлу.
    :param output_file: Путь к выходному видеофайлу.
    :param silence_threshold: Порог амплитуды, ниже которого считаем тишину (0.005 = 0.5%).
    :param min_duration: Минимальная длительность тишины для удаления (в секундах).
    start_periods=1: Указывает, что тишина должна начаться после одного периода тишины.
    start_threshold=0.01: Указывает порог амплитуды для начала тишины. Значение 0.01 соответствует 1% от максимальной амплитуды.
    start_silence=0.5: Минимальная длительность тишины для её удаления (если тишина меньше 0.5 секунд, она не будет удалена).
    stop_periods=-1: Указывает, что период тишины должен заканчиваться, когда звук снова превысит порог амплитуды.
    stop_threshold=0.01: Порог амплитуды для окончания тишины.
    stop_silence=0.5: Минимальная длительность звука после тишины, чтобы считать её оконченной.
    min_duration=0.5: Это заданный минимум для длительности тишины (в секундах), чтобы она была удалена.
    """

    # Формируем команду для FFmpeg с фильтром silenceremove
    audio_filter = (
        f"silenceremove=start_periods=1:start_threshold={silence_threshold}:"
        f"start_silence={min_duration}:stop_periods=-1:stop_threshold={silence_threshold}:"
        f"stop_silence={min_duration}"
    )

    # Запускаем процесс обработки с использованием ffmpeg-python
    (
        ffmpeg
        .input(input_file)
        .output(output_file, af=audio_filter)
        .run(overwrite_output=True)
    )