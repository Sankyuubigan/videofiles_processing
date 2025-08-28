use iced::{
    widget::{button, column, container, row, text, Space},
    Element, Length, Renderer, Theme,
    advanced::renderer::Style,
};
use crate::ffmpeg_utils::VideoInfo;

#[derive(Debug, Clone)]
pub enum ModalMessage {
    Close,
}

pub struct State {
    kind: Kind,
}

impl State {
    pub fn new(kind: Kind) -> Self {
        Self { kind }
    }
    
    pub fn update(&mut self, message: ModalMessage) {
        match message {
            ModalMessage::Close => {
                // Закрываем модальное окно
                // В реальном приложении здесь нужно установить состояние модального окна в None
            }
        }
    }
    
    pub fn view<'a>(
        &'a self, 
        content: Element<'a, crate::Message, Theme, Renderer>, 
        modal_message_mapper: fn(ModalMessage) -> crate::Message
    ) -> Element<'a, crate::Message, Theme, Renderer> {
        let modal = match self.kind {
            Kind::Info(ref info) => {
                if let Some(info) = info {
                    self.view_info(info, modal_message_mapper)
                } else {
                    container(text("Нет информации")).into()
                }
            },
        };
        
        container(
            column![
                content,
                modal.map(modal_message_mapper),
            ]
            .width(Length::Fill)
            .height(Length::Fill),
        )
        .width(Length::Fill)
        .height(Length::Fill)
        .into()
    }
    
    fn view_info(&self, info: &VideoInfo, modal_message_mapper: fn(ModalMessage) -> crate::Message) -> Element<ModalMessage, Theme, Renderer> {
        container(
            column![
                row![
                    text("Информация о файле").size(20),
                    Space::with_width(Length::Fill),
                    button("Закрыть")
                        .on_press(ModalMessage::Close)
                        .width(100),
                ]
                .padding(10),
                column![
                    row![
                        text("Путь:").width(100),
                        text(info.path.to_string_lossy().to_string()),
                    ],
                    row![
                        text("Размер:").width(100),
                        text(format!("{:.2} МБ", info.size_bytes as f64 / 1024.0 / 1024.0)),
                    ],
                    row![
                        text("Длительность:").width(100),
                        text(format!("{:.2} сек", info.duration)),
                    ],
                    row![
                        text("Разрешение:").width(100),
                        text(format!("{}x{}", info.width, info.height)),
                    ],
                    row![
                        text("FPS:").width(100),
                        text(format!("{:.2}", info.fps)),
                    ],
                    row![
                        text("Битрейт:").width(100),
                        text(format!("{} кбит/с", info.bitrate / 1000)),
                    ],
                    row![
                        text("Требуется VFR fix:").width(100),
                        text(if info.needs_vfr_fix { "Да" } else { "Нет" }),
                    ],
                    row![
                        text("Примерный размер после сжатия:").width(100),
                        text(format!("{:.2} МБ", info.estimated_compressed_size)),
                    ],
                    row![
                        text("GPU:").width(100),
                        text(&info.gpu_info),
                    ],
                    row![
                        text("Режим обработки:").width(100),
                        text(&info.processing_mode),
                    ],
                ]
                .spacing(10),
            ]
            .spacing(10)
            .max_width(600)
            .height(400),
        )
        .padding(20)
        .style(|_theme: &Theme| Style {
            background: Some(iced::Background::Color(iced::Color {
                r: 0.3,
                g: 0.3,
                b: 0.3,
                a: 0.95,
            })),
            border: iced::Border {
                color: iced::Color {
                    r: 0.5,
                    g: 0.5,
                    b: 0.5,
                    a: 1.0,
                },
                width: 1.0,
                radius: 5.0.into(),
            },
            shadow: iced::Shadow::default(),
            text_color: None,
        })
        .center_x()
        .center_y()
        .width(Length::Fill)
        .height(Length::Fill)
        .into()
    }
}

#[derive(Debug, Clone)]
pub enum Kind {
    Info(Option<VideoInfo>),
}