
export const BASE_PATH = '/__BASE_PATH__';
export const DEBUG = BASE_PATH.includes('__' + 'BASE' + '_' + 'PATH' + '__');   // it is split to not get replaced by the start.sh script as well
export const API_BASE = DEBUG ? 'http://localhost:8888/api' : '/__API_PATH__';


export const HUB_API_BASE = '/hub/api';

export const USER = BASE_PATH.split('/')[2] || 'user';
