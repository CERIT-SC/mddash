import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Routes, Route, BrowserRouter } from 'react-router-dom'

import './main.css'

import Layout from './Layout'
import Home from './pages/Home'
import New from './pages/New'
import Wizard from './pages/Wizard'


createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <BrowserRouter>
            <Routes>
                <Route path="/__BASE_PATH__/" element={<Layout />}>
                    <Route index element={<Home />} />
                    <Route path="/__BASE_PATH__/new" element={<New />} />
                    <Route path="/__BASE_PATH__/wizard" element={<Wizard />} />
                </Route>
            </Routes>
        </BrowserRouter>
    </StrictMode>
)
