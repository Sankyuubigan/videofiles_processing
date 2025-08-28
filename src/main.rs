use iced::{
    widget::{button, column, container, progress_bar, row, text, pick_list, slider, Space},
    Application, Command, Element, Length, Settings, Subscription, executor,
};
use iced::Event;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use modals::ModalMessage;
use crate::ffmpeg_utils::{FFmpegUtils, VideoInfo};
use crate::config::{AppConfig, OutputFormat, DEFAULT_OUTPUT_FORMAT};

mod config;
mod ffmpeg_utils;
mod ffmpeg_bin;
mod ui;
mod modals;

pub fn main() -> iced::Result {
    VideoCompressor::run(Settings {
        default_text_size: iced::Pixels(14.0),
        ..Settings::default()
    })
}

#[derive(Debug, Clone)]
enum Message {
    FileDropped(PathBuf),
    FileSelected(Option<PathBuf>),
    FormatSelected(OutputFormat),
    CrfChanged(u8),
    ForceVfrFixToggled(bool),
    Compress,
    ShowInfo,
    CompressionProgress(f32),
    CompressionComplete(Result<String, String>),
    InfoReady(VideoInfo),
    ModalMessage(ModalMessage),
    None,
}

struct VideoCompressor {
    input_file: Option<PathBuf>,
    output_format: OutputFormat,
    crf_value: u8,
    force_vfr_fix: bool,
    is_processing: bool,
    progress: f32,
    status_message: String,
    video_info: Option<VideoInfo>,
    ffmpeg_utils: Arc<Mutex<FFmpegUtils>>,
    modal_state: Option<modals::State>,
    file_queue: Vec<PathBuf>,
    current_file_index: Option<usize>,
}

impl Application for VideoCompressor {
    type Message = Message;
    type Executor = executor::Default;
    type Theme = iced::Theme;
    type Flags = ();

    fn new(_flags: ()) -> (Self, Command<Message>) {
        let config = AppConfig::default();
        let ffmpeg_utils = FFmpegUtils::new();
        
        (
            Self {
                input_file: None,
                output_format: DEFAULT_OUTPUT_FORMAT,
                crf_value: config.get_default_crf(&DEFAULT_OUTPUT_FORMAT),
                force_vfr_fix: false,
                is_processing: false,
                progress: 0.0,
                status_message: "Готов к работе".to_string(),
                video_info: None,
                ffmpeg_utils: Arc::new(Mutex::new(ffmpeg_utils)),
                modal_state: None,
                file_queue: Vec::new(),
                current_file_index: None,
            },
            Command::none(),
        )
    }

    fn title(&self) -> String {
        String::from("Video Compressor")
    }

    fn update(&mut self, message: Message) -> Command<Message> {
        match message {
            Message::FileDropped(path) => {
                self.file_queue.push(path);
                if self.input_file.is_none() && !self.is_processing {
                    self.process_next_file();
                }
                self.status_message = format!("В очереди {} файлов", self.file_queue.len());
                Command::none()
            }
            Message::FileSelected(path) => {
                if let Some(p) = path {
                    self.file_queue.push(p);
                    if self.input_file.is_none() && !self.is_processing {
                        self.process_next_file();
                    }
                    self.status_message = format!("В очереди {} файлов", self.file_queue.len());
                }
                Command::none()
            }
            Message::FormatSelected(format) => {
                self.output_format = format;
                let config = AppConfig::default();
                self.crf_value = config.get_default_crf(&format);
                Command::none()
            }
            Message::CrfChanged(crf) => {
                self.crf_value = crf;
                Command::none()
            }
            Message::ForceVfrFixToggled(value) => {
                self.force_vfr_fix = value;
                Command::none()
            }
            Message::Compress => {
                if self.input_file.is_none() && self.file_queue.is_empty() {
                    self.status_message = "Сначала выберите файл".to_string();
                    return Command::none();
                }
                
                if self.input_file.is_none() && !self.file_queue.is_empty() {
                    self.process_next_file();
                    return Command::none();
                }
                
                self.is_processing = true;
                self.progress = 0.0;
                self.status_message = "Обработка...".to_string();
                
                let input_file = self.input_file.clone().unwrap();
                let output_format = self.output_format;
                let crf_value = self.crf_value;
                let force_vfr_fix = self.force_vfr_fix;
                
                Command::perform(
                    async move {
                        // Получаем доступ к FFmpegUtils и сразу освобождаем блокировку
                        let input_path = input_file.clone();
                        let output_format = output_format;
                        let crf_value = crf_value;
                        let force_vfr_fix = force_vfr_fix;
                        
                        // Создаем новый экземпляр FFmpegUtils для асинхронной операции
                        let utils = FFmpegUtils::new();
                        utils.compress_video(
                            &input_path,
                            output_format,
                            crf_value,
                            force_vfr_fix,
                            |_progress| {
                                // В реальном приложении здесь нужно отправлять сообщение о прогрессе
                                // Для упрощения примера опустим
                            }
                        ).await
                    },
                    |result| Message::CompressionComplete(result.map(|p| p.to_string_lossy().to_string()))
                )
            }
            Message::ShowInfo => {
                if self.input_file.is_none() {
                    self.status_message = "Сначала выберите файл".to_string();
                    return Command::none();
                }
                
                let input_file = self.input_file.clone().unwrap();
                
                Command::perform(
                    async move {
                        // Создаем новый экземпляр FFmpegUtils для асинхронной операции
                        let utils = FFmpegUtils::new();
                        utils.get_video_info(&input_file).await
                    },
                    |info| Message::InfoReady(info)
                )
            }
            Message::CompressionProgress(progress) => {
                self.progress = progress;
                Command::none()
            }
            Message::CompressionComplete(result) => {
                self.is_processing = false;
                match result {
                    Ok(output_path) => {
                        self.status_message = format!("Готово: {}", output_path);
                    }
                    Err(error) => {
                        self.status_message = format!("Ошибка: {}", error);
                    }
                }
                
                // Обрабатываем следующий файл в очереди
                self.process_next_file();
                Command::none()
            }
            Message::InfoReady(info) => {
                self.video_info = Some(info.clone());
                self.modal_state = Some(modals::State::new(modals::Kind::Info(Some(info))));
                Command::none()
            }
            Message::ModalMessage(msg) => {
                if let Some(ref mut modal_state) = self.modal_state {
                    modal_state.update(msg);
                    if matches!(msg, ModalMessage::Close) {
                        self.modal_state = None;
                    }
                }
                Command::none()
            }
            Message::None => Command::none(),
        }
    }

    fn view(&self) -> Element<Message> {
        let content = column![
            // Заголовок
            container(text("Video Compressor").size(24))
                .width(Length::Fill)
                .center_x()
                .padding(10),
            
            // Выбор файла
            container(
                column![
                    text("1. Выбор видеофайла").size(16),
                    row![
                        button("Выбрать файл")
                            .on_press(Message::FileSelected(None))
                            .width(Length::FillPortion(1)),
                        Space::with_width(Length::FillPortion(1)),
                        button("Информация о файле")
                            .on_press(Message::ShowInfo)
                            .width(Length::FillPortion(1))
                    ]
                    .spacing(10),
                    text(if let Some(ref file) = self.input_file {
                        format!("Обрабатывается: {:?}", file.file_name())
                    } else if !self.file_queue.is_empty() {
                        format!("В очереди {} файлов", self.file_queue.len())
                    } else {
                        "Файл не выбран".to_string()
                    })
                    .width(Length::Fill)
                ]
            )
            .padding(10)
            .width(Length::Fill)
            .style(ui::container_style),
            
            // Настройки сжатия
            container(
                column![
                    text("2. Настройки сжатия").size(16),
                    row![
                        text("Формат:"),
                        pick_list(
                            OutputFormat::all(),
                            Some(self.output_format),
                            Message::FormatSelected
                        )
                        .width(Length::FillPortion(2)),
                        Space::with_width(Length::FillPortion(1)),
                        text(format!("CRF: {}", self.crf_value)),
                        slider(0..=51, self.crf_value, Message::CrfChanged)
                            .width(Length::FillPortion(4))
                    ]
                    .spacing(10),
                    row![
                        text("Принудительная починка VFR:"),
                        iced::widget::checkbox("", self.force_vfr_fix).on_toggle(Message::ForceVfrFixToggled)
                    ]
                    .spacing(10)
                ]
            )
            .padding(10)
            .width(Length::Fill)
            .style(ui::container_style),
            
            // Запуск
            container(
                column![
                    text("3. Запуск").size(16),
                    button("Сжать видео")
                        .on_press(Message::Compress)
                        .width(Length::Fill),
                    progress_bar(0.0..=1.0, self.progress)
                        .width(Length::Fill),
                    text(&self.status_message)
                ]
            )
            .padding(10)
            .width(Length::Fill)
            .style(ui::container_style),
        ]
        .spacing(20)
        .padding(20)
        .width(Length::Fill)
        .height(Length::Fill);
        
        // Модальное окно, если активно
        if let Some(ref modal_state) = self.modal_state {
            modal_state.view(content.into(), |msg| Message::ModalMessage(msg))
        } else {
            content.into()
        }
    }

    fn subscription(&self) -> Subscription<Message> {
        iced::event::listen_with(|event, _status| {
            if let Event::Window(_id, iced::window::Event::FileDropped(path)) = event {
                Some(Message::FileDropped(path))
            } else {
                None
            }
        })
    }
}

impl VideoCompressor {
    fn process_next_file(&mut self) {
        if !self.file_queue.is_empty() {
            self.input_file = Some(self.file_queue.remove(0));
            self.current_file_index = Some(0);
            self.status_message = format!("Обрабатывается: {:?}", self.input_file.as_ref().unwrap().file_name());
            
            // Автоматически начинаем обработку следующего файла
            self.update(Message::Compress);
        } else {
            self.input_file = None;
            self.current_file_index = None;
            self.status_message = "Готов к работе".to_string();
        }
    }
}