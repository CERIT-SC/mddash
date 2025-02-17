import axios from 'axios';

import { API_BASE } from './const';


export const get_experiments = async () => {
    const response = await axios.get(`${API_BASE}/experiments`);
    return response.data;
};


export const create_experiment = async (formData: FormData) => {
    const response = await axios.post(`${API_BASE}/experiments`, formData);

    if (response.data.status === 'error')
        throw new Error(response.data.message || 'Failed to create experiment');

    return response.data;
}

export const get_experiment = async (id: string) => {
    const response = await axios.get(`${API_BASE}/experiments/${id}`);
    return response.data;
}


export const delete_experiment = async (id: string) => {
    const response = await axios.delete(`${API_BASE}/experiments/${id}`);
    return response.data;
};
