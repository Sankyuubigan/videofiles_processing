// Theme не используется в новой реализации

pub fn container_style(theme: &iced::Theme) -> iced::widget::container::Appearance {
    // Используем базовый стиль контейнера
    let palette = theme.extended_palette();

    iced::widget::container::Appearance {
        background: Some(iced::Background::Color(palette.background.weak.color)),
        border: iced::Border {
            color: palette.background.strong.color,
            width: 1.0,
            radius: 5.0.into(),
        },
        shadow: iced::Shadow::default(),
        text_color: Some(palette.background.base.text),
    }
}