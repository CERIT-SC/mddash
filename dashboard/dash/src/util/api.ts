import axios from 'axios';

import { API_BASE } from './const';


export class ApiError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ApiError';
        Object.setPrototypeOf(this, ApiError.prototype);
    }
}


const data_or_throw = (response: any) => {
    if (response.data.status === 'error')
        throw new ApiError(response.data.message || 'Failed to perform operation.');

    return response.data;
}


export const get_experiments = async () => {
    const response = await axios.get(`${API_BASE}/experiments`);
    return data_or_throw(response);
}


export const get_experiment = async (id: string) => {
    const response = await axios.get(`${API_BASE}/experiments/${id}`);
    return data_or_throw(response);
}


export const create_experiment = async (formData: FormData) => {
    const response = await axios.post(`${API_BASE}/experiments`, formData);
    return data_or_throw(response);
}


export const delete_experiment = async (id: string) => {
    const response = await axios.delete(`${API_BASE}/experiments/${id}`);
    return data_or_throw(response);
}


export const get_notebook = async (id: string) => {
    const response = await axios.get(`${API_BASE}/experiments/${id}/notebook`);
    return data_or_throw(response);
}


export const spawn_notebook = async (id: string) => {
    const response = await axios.post(`${API_BASE}/experiments/${id}/notebook`);
    return data_or_throw(response);
}


export const delete_notebook = async (id: string) => {
    const response = await axios.delete(`${API_BASE}/experiments/${id}/notebook`);
    return data_or_throw(response);
}
