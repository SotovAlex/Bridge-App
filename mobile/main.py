from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.core.window import Window
import asyncio
import sys
import os

# Добавляем путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from async_client import client, run_async_task


class BridgeApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages = []

    def build(self):
        Window.size = (400, 600)
        self.title = "Bridge - Connect the World"

        # Главный layout
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Статус бар
        self.status_label = Label(
            text="Disconnected",
            size_hint_y=0.1,
            color=(0.2, 0.6, 0.8, 1)
        )
        main_layout.add_widget(self.status_label)

        # Область сообщений
        scroll_view = ScrollView(size_hint_y=0.6)
        self.chat_label = Label(
            text="Welcome to Bridge!\nPress 'Connect' to find a conversation partner.\n\n",
            size_hint_y=None,
            text_size=(380, None),
            halign='left',
            valign='top'
        )
        self.chat_label.bind(texture_size=self.chat_label.setter('size'))
        scroll_view.add_widget(self.chat_label)
        main_layout.add_widget(scroll_view)

        # Панель управления
        control_layout = BoxLayout(orientation='horizontal', size_hint_y=0.15, spacing=10)

        self.connect_btn = Button(text="Find Partner")
        self.connect_btn.bind(on_press=self.connect_to_server)
        control_layout.add_widget(self.connect_btn)

        self.disconnect_btn = Button(text="Disconnect", disabled=True)
        self.disconnect_btn.bind(on_press=self.disconnect_from_server)
        control_layout.add_widget(self.disconnect_btn)

        main_layout.add_widget(control_layout)

        # Поле ввода сообщения (покажем только когда есть соединение)
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=0.15, spacing=10)

        self.message_input = TextInput(
            hint_text="Type your message here...",
            multiline=False,
            disabled=True
        )
        self.message_input.bind(on_text_validate=self.send_message)
        input_layout.add_widget(self.message_input)

        self.send_btn = Button(text="Send", size_hint_x=0.3, disabled=True)
        self.send_btn.bind(on_press=self.send_message)
        input_layout.add_widget(self.send_btn)

        main_layout.add_widget(input_layout)

        # Настраиваем callback-функции для клиента
        client.set_callbacks(self.add_message, self.update_status)

        # Добавляем выбор страны перед кнопкой подключения
        country_layout = BoxLayout(orientation='horizontal', size_hint_y=0.1, spacing=10)
        country_layout.add_widget(Label(text="Country:", size_hint_x=0.4))

        self.country_spinner = Spinner(
            text='Russia',
            values=('Russia', 'USA', 'Germany', 'Japan', 'Brazil', 'France', 'UK', 'Australia'),
            size_hint_x=0.6
        )
        country_layout.add_widget(self.country_spinner)
        main_layout.add_widget(country_layout)

        return main_layout

    def connect_to_server(self, instance):
        """Подключаемся к серверу"""
        self.update_status("Connecting...")
        self.connect_btn.disabled = True

        country = self.country_spinner.text
        language = "en"  # Пока используем английский для всех

        print(f"Connecting as: {country}")  # Для дебага

        # Запускаем подключение в отдельном потоке
        run_async_task(client.connect(country, language))

        # Включаем кнопку отключения
        self.disconnect_btn.disabled = False

    def disconnect_from_server(self, instance):
        """Отключаемся от сервера"""
        run_async_task(client.disconnect())
        self.connect_btn.disabled = False
        self.disconnect_btn.disabled = True
        self.message_input.disabled = True
        self.send_btn.disabled = True

    def send_message(self, instance):
        """Отправляем сообщение"""
        text = self.message_input.text.strip()
        if text and client.connected:
            # НЕ добавляем сообщение сразу в интерфейс
            # Ждем пока сервер перешлет его партнеру и вернет обработа
            print(f"Attempting to send message: {text}")  # Дебаг
            run_async_task(client.send_message(text))
            self.message_input.text = ""

    def update_status(self, status):
        """Обновляем статус соединения"""
        self.status_label.text = status
        print(f"Status: {status}")  # Для дебага

        # Включаем/выключаем элементы в зависимости от статуса
        if "Connected with partner" in status:
            self.message_input.disabled = False
            self.send_btn.disabled = False
        elif "Disconnected" in status:
            self.message_input.disabled = True
            self.send_btn.disabled = True
            self.connect_btn.disabled = False
            self.disconnect_btn.disabled = True

    def add_message(self, message):
        """Добавляем сообщение в чат"""
        current_text = self.chat_label.text
        if len(current_text.split('\n')) > 20:  # Ограничиваем историю
            current_text = '\n'.join(current_text.split('\n')[-15:])

        self.chat_label.text = current_text + f"\n{message}"

        # Прокручиваем вниз
        scroll_parent = self.chat_label.parent
        if scroll_parent:
            scroll_parent.scroll_y = 0

    def on_stop(self):
        """При закрытии приложения отключаемся от сервера"""
        run_async_task(client.disconnect())


if __name__ == "__main__":
    BridgeApp().run()