use iced::{
    Color,
    widget::container,
    advanced::renderer::Style,
};

pub fn container_style(_theme: &iced::Theme) -> Style {
    Style {
        background: Some(iced::Background::Color(Color {
            r: 0.2,
            g: 0.2,
            b: 0.2,
            a: 1.0,
        })),
        border: iced::Border {
            color: Color {
                r: 0.3,
                g: 0.3,
                b: 0.3,
                a: 1.0,
            },
            width: 1.0,
            radius: 5.0.into(),
        },
        shadow: iced::Shadow::default(),
        text_color: None,
    }
}