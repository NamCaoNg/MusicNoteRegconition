import { Copyright } from 'lucide-react';

export default function Footer() {
    return (
        <footer className="app-footer">
            <p>
                <Copyright className="footer-icon" aria-hidden="true" />
                {new Date().getFullYear()} <a href="/">MyOMR</a> - Optical Music Recognition.
                Built with love for musicians everywhere.
            </p>
        </footer>
    );
}