"""
Основной модуль мобильного клиента Bridge-App
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window

class BridgeApp(App):
    def build(self):
        self.title = "Bridge App"
        Window.size = (360, 640)  # Размер окна для мобильного вида
        return MainScreen()

class MainScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        
    # Здесь будет основная логика интерфейса

if __name__ == '__main__':
    BridgeApp().run()
