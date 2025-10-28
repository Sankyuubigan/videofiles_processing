from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton
from PySide6.QtGui import QFont


class VideoInfoDialog(QDialog):
    def __init__(self, video_info, parent=None):
        super().__init__(parent)
        self.video_info = video_info
        self.setWindowTitle("Информация о видео")
        self.setModal(True)
        self.resize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        title = QLabel("Информация о файле")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        info_text = QTextBrowser()
        audio_info = ""
        audio_tracks = self.video_info.get('audio_tracks', [])
        if audio_tracks:
            audio_info = f"<b>Аудиодорожки:</b> {len(audio_tracks)}<br>"
            for i, track in enumerate(audio_tracks):
                lang = track.get('language', 'und')
                title_str = track.get('title', f'Audio {i+1}')
                channels = track.get('channels', 0)
                audio_info += f"&nbsp;&nbsp;• {title_str} ({lang}, {channels}ch)<br>"
        else:
            audio_info = "<b>Аудиодорожки:</b> Не найдены<br>"
        
        needs_vfr_text = "Да" if self.video_info.get('needs_vfr_fix') else "Нет"
        
        info_html = f"""
        <b>Путь:</b> {self.video_info.get('path', 'N/A')}<br>
        <b>Размер:</b> {self.video_info.get('size_mb', 0):.2f} МБ<br>
        <b>Длительность:</b> {self.video_info.get('duration', 0):.2f} сек<br>
        <b>Разрешение:</b> {self.video_info.get('width', 0)}x{self.video_info.get('height', 0)}<br>
        <b>FPS:</b> {self.video_info.get('fps', 0):.2f}<br>
        <b>Битрейт видео:</b> {self.video_info.get('video_bitrate', 0) // 1000} кбит/с<br>
        <b>Битрейт аудио:</b> {self.video_info.get('audio_bitrate', 0) // 1000} кбит/с<br>
        <b>Требуется VFR fix:</b> {needs_vfr_text}<br>
        <b>Примерный размер после сжатия:</b> {self.video_info.get('estimated_size_mb', 0):.2f} МБ<br>
        {audio_info}
        <b>GPU:</b> {self.video_info.get('gpu_info', 'N/A')}<br>
        <b>Режим обработки:</b> {self.video_info.get('processing_mode', 'N/A')}
        """
        info_text.setHtml(info_html)
        layout.addWidget(info_text)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)