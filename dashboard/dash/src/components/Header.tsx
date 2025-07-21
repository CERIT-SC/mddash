import { Link, useLocation } from "react-router-dom";
import { Typography, IconButton, Toolbar, AppBar, Stack } from "@mui/material";
import { HubTwoTone, DashboardTwoTone } from "@mui/icons-material";

import { BASE_PATH } from "../util/const";

const Header = () => {
    const location = useLocation();
    const notHome = location.pathname !== BASE_PATH && location.pathname !== BASE_PATH + "/";

    return (
        <AppBar position="static" color="primary" elevation={0}>
            <Toolbar sx={{ minHeight: "64px", px: 2 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ width: "100%" }}>
                    {/* Fixed-width left icon container */}
                    <Stack direction="row" alignItems="center" sx={{ width: 96 }}>
                        <IconButton size="large" sx={{ color: "white" }} href="/hub/home" title="Back to JupyterHub">
                            <HubTwoTone />
                        </IconButton>
                        {notHome && (
                            <IconButton
                                size="large"
                                sx={{ color: "white" }}
                                component={Link}
                                to={BASE_PATH}
                                title="Back to Dashboard"
                            >
                                <DashboardTwoTone />
                            </IconButton>
                        )}
                    </Stack>
                    <div style={{ flex: 1, textAlign: "center" }}>
                        <Link to={BASE_PATH} style={{ textDecoration: "none", color: "white" }}>
                            <Typography variant="h1">FAIR MD Dash</Typography>
                        </Link>
                    </div>
                    {/* Fixed-width right spacer to match left */}
                    <Stack sx={{ width: 96 }} />
                </Stack>
            </Toolbar>
        </AppBar>
    );
};

export default Header;
