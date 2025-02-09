c = get_config()

# c.NotebookApp.notebook_dir = '/home/jovyan/work/experiment'

c.ServerProxy.servers = {
    'dash': {
        'command': None,
        'absolute_url': False,
        'port': 5000,
        'url_prefix': '/dash',
        'map_url': True,  # Enable path forwarding
        'launcher_entry': {
            'title': 'Dashboard',
            'icon_path': ''
        }
    },

    # 'dash-api': {
    #     'command': None,
    #     'absolute_url': False,
    #     'port': 3000,
    #     'url_prefix': '/api',
    #     'map_url': True,
    #     'launcher_entry': {
    #         'title': 'API',
    #         'icon_path': ''
    #     }
    # }
}
