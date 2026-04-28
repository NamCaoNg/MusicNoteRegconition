import { Link } from 'react-router-dom';
import { Clock, Download, Sun, Upload } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function HomePage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="home-page">
      {/* ── Navigation ── */}
      <nav className="home-nav">
        <Link to="/" className="home-nav-brand">
          <img
            src="/logo.png"
            alt="MyOMR logo"
            className="navbar-icon"
            width="26"
            height="26"
          />
          <span className="navbar-title">MyOMR</span>
        </Link>
        <div className="home-nav-actions">
          {isAuthenticated ? (
            <>
              <Link to="/upload" className="btn btn-outline btn-sm">Upload</Link>
              <Link to="/history" className="btn btn-primary btn-sm">Dashboard</Link>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-outline btn-sm">Sign In</Link>
              <Link to="/register" className="btn btn-primary btn-sm">Get Started</Link>
            </>
          )}
        </div>
      </nav>

      {/* ── Hero Section ── */}
      <section className="hero-section">
        <div className="hero-content">
          <h1 className="hero-title">
            Transform Sheet Music into{' '}
            <span className="hero-title-gradient">Digital Formats</span>
          </h1>

          <p className="hero-description">
            Upload your music score images and let AI convert them into
            MusicXML and MIDI files - instantly and accurately. Perfect for
            musicians, composers, and researchers.
          </p>

          <div className="hero-actions">
            {isAuthenticated ? (
              <>
                <Link to="/upload" className="btn btn-primary">
                  <Upload className="btn-icon" />
                  Upload
                </Link>
                <Link to="/history" className="btn btn-outline">
                  <Clock className="btn-icon" />
                  History
                </Link>
              </>
            ) : (
              <>
                <Link to="/register" className="btn btn-primary">
                  Get Started - It's Free
                </Link>
                <Link to="/login" className="btn btn-outline">
                  Sign In to Your Account
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ── Features Section ── */}
      <section className="features-section">
        <div className="section-header">
          <h2 className="section-title">Everything You Need for OMR</h2>
          <p className="section-description">
            A streamlined workflow that takes you from a paper score to digital
            music formats in seconds.
          </p>
        </div>

        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <Upload />
            </div>
            <h3>Smart Upload</h3>
            <p>
              Drag & drop or browse for your score images. Supports JPG, PNG,
              BMP, TIFF, and WebP formats up to 20 MB.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <Sun />
            </div>
            <h3>AI Recognition</h3>
            <p>
              Advanced deep learning models analyze your scores, detecting notes,
              rests, dynamics, and articulations with high accuracy.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <Download />
            </div>
            <h3>Export Results</h3>
            <p>
              Download your recognized scores as MusicXML for notation software
              or MIDI for playback and production.
            </p>
          </div>
        </div>
      </section>

    </div>
  );
}
